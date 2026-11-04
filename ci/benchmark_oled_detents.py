#!/usr/bin/env python3
"""Replay OLED menu detents and model their serial traffic offline."""
import argparse
from functools import lru_cache
from itertools import islice
import json
from pathlib import Path
from statistics import median
import sys


PAGES = ('main', 'zortrax', 'maintenance', 'material', 'settings', 'information',
         'setting_sort_mode', 'setting_oled_brightness', 'setting_led_brightness')
TOKEN_START = 4096  # Stable native VLQ token width over these menu traces.


def decode_pixels(ops):
    result = bytearray()
    for _, (dc, encoding, length, data), _ in ops:
        assert dc == 1 and 0 < len(data) <= 32 and 0 < length <= 256
        start = len(result)
        if encoding:
            pos = 0
            while pos < len(data):
                code = data[pos]
                size = (code & 127) + 1
                pos += 1
                if code & 128:
                    result.extend(bytes([data[pos]]) * size)
                    pos += 1
                else:
                    result.extend(data[pos:pos + size])
                    pos += size
            assert pos == len(data)
        else:
            result.extend(data)
        assert len(result) - start == length
    return result


def shorter_raw_prefix(data, fast_blocks):
    """Test a packet boundary before a long repeat crossed by a raw packet."""
    offset = 0
    stream = iter(fast_blocks(data))
    while offset < len(data):
        operation = next(stream)
        _, (_, encoding, length, _), _ = operation
        if not encoding:
            stop = min(offset + length, len(data) - 11)
            cut = next((i for i in range(offset + 1, stop)
                        if data[i] != data[i - 1] and data[i:i+12] == data[i:i+1] * 12), None)
            if cut is not None:
                prefix = data[offset:cut]
                yield ('burst', (1, 0, len(prefix), prefix), 0.)
                offset = cut
                stream = iter(fast_blocks(data[offset:]))
                continue
        yield operation
        offset += length


def bounds(points):
    ys, cols = zip(*points)
    return min(ys), max(ys), min(cols), max(cols)


def gap_splits(before, after, window):
    """Yield two tight rectangles divided by an entirely unchanged line."""
    y0, y1, c0, c1 = window
    points = [(y, c) for y in range(y0, y1+1) for c in range(c0, c1+1)
              if before[128*y+2*c:128*y+2*c+2] != after[128*y+2*c:128*y+2*c+2]]
    for axis in (0, 1):
        occupied = sorted({point[axis] for point in points})
        for first, second in zip(occupied, occupied[1:]):
            if second > first + 1:
                yield (bounds([p for p in points if p[axis] <= first]),
                       bounds([p for p in points if p[axis] >= second]))


def benchmark(session, transport, parser, envelope):
    burst = parser.messages_by_name['m300_oled_burst']
    ack = parser.messages_by_name['m300_oled_ack']
    traces = []
    with session() as printer:
        menu, oled, now = printer.menu, printer.oled, printer.now
        for page in PAGES:
            menu.page = page
            frames = []
            for selection, _ in enumerate(oled._rows(now)[1]):
                oled.selection = selection
                oled._render(now)
                frames.append(oled._render_wire)
            for index, (before, after) in enumerate(zip(frames, frames[1:])):
                traces.extend(((page, index, 1, before, after),
                               (page, index + 1, -1, after, before)))

    def score(plans):
        packets = [op for _, ops in plans for op in ops]
        tokens = range(TOKEN_START, TOKEN_START + len(packets))
        tx_lengths = [len(burst.encode([token, *op[1]])) for token, op in zip(tokens, packets)]
        rx_lengths = [len(ack.encode([token])) for token in tokens]
        return {'bursts': len(packets), 'uart_tx_isolated': sum(tx_lengths) + envelope*len(packets),
                'uart_ack_isolated': sum(rx_lengths) + envelope*len(packets),
                'uart_total_isolated': sum(tx_lengths) + sum(rx_lengths) + 2*envelope*len(packets),
                'payload_bytes': sum(len(op[1][3]) for op in packets)}

    results = []
    for page, selection, delta, before, after in traces:
        outer = transport.diff_window(before, after)
        if outer is None:
            continue

        @lru_cache(maxsize=None)
        def packets(window, lookahead):
            default = transport.fast_frame_operations(after, *window)
            headers = tuple(islice(default, 5))
            pixels = tuple(default)
            if lookahead:
                pixels = tuple(shorter_raw_prefix(decode_pixels(pixels), transport.fast_blocks))
            return headers + pixels

        baseline = transport.diff_regions(before, after)
        windows = [baseline, (outer,), *gap_splits(before, after, outer)]
        plans = [[(window, packets(window, False)) for window in plan] for plan in windows]
        runtime_ops = transport.optimized_frame_operations(before, after, baseline)
        runtime_plan = next(plan for plan in plans
                            if tuple(op for _, ops in plan for op in ops) == runtime_ops)
        packet_alt = [(window, packets(window, True)) for window in baseline]
        variants = {'baseline': [plans[0]], 'window_only': plans,
                    'release_planner': [runtime_plan],
                    'packet_only': [plans[0], packet_alt],
                    'combined': plans + [packet_alt] + [
                        [(window, packets(window, True)) for window in plan]
                        for plan in windows[1:]]}

        measured = {}
        for name, choices in variants.items():
            def cost(choice):
                sample = score(choice)
                return sample['uart_total_isolated'], sample['bursts']
            best = min(choices, key=cost)
            reconstructed = bytearray(before)
            for (y0, y1, c0, c1), ops in best:
                assert 0 <= y0 <= y1 < 64 and 0 <= c0 <= c1 < 64
                assert [op[1][3] for op in ops[:5]] == [
                    b'\x15', bytes([0x1c+c0, 0x1c+c1]), b'\x75', bytes([y0, y1]), b'\x5c']
                pixels = decode_pixels(ops[5:])
                width = 2 * (c1-c0+1)
                assert len(pixels) == width * (y1-y0+1)
                for row in range(y0, y1+1):
                    offset = 128*row + 2*c0
                    start = (row-y0)*width
                    reconstructed[offset:offset+width] = pixels[start:start+width]
            assert reconstructed == after, (page, selection, delta, name)
            measured[name] = score(best)
        results.append(dict(page=page, selection=selection, detents=delta, **measured))

    assert len(results) >= 20
    summaries = {}
    for name in variants:
        summary = {key: sum(row[name][key] for row in results) for key in results[0][name]}
        summary['median_uart_bytes_per_detent'] = median(row[name]['uart_total_isolated']
                                                          for row in results)
        summary['median_bursts_per_detent'] = median(row[name]['bursts'] for row in results)
        summary['no_worse_in_model'] = all(
            row[name]['uart_total_isolated'] <= row['baseline']['uart_total_isolated']
            for row in results)
        summary['improved_detents'] = sum(
            row[name]['uart_total_isolated'] < row['baseline']['uart_total_isolated']
            for row in results)
        summaries[name] = summary
    assert summaries['release_planner']['no_worse_in_model']
    assert summaries['release_planner']['improved_detents'] > 0
    return {'dictionary': parser.version, 'changed_detents': len(results),
            'pages': sorted({row['page'] for row in results}),
            'model': 'One native serial envelope per OLED burst and per application ACK. '
                     'Real transport can batch messages. Retries and other traffic excluded.',
            'runtime_modified': False, 'physical_hardware': False, 'totals': summaries,
            'traces': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--dictionary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(args.package.resolve()), str((args.package / 'tests').resolve()),
                    str((args.upstream / 'klippy').resolve())]
    from msgproto import MESSAGE_MIN, MessageParser
    from payload import m300_oled_transport
    from test_settings_information import session

    protocol = MessageParser()
    protocol.process_identify(args.dictionary.read_bytes(), decompress=False)
    report = benchmark(session, m300_oled_transport, protocol, MESSAGE_MIN)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'traces'}, indent=2))


if __name__ == '__main__':
    main()
