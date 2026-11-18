# Marcin Kowalik <mkowalik@agh.edu.pl>
# check_fluidd_sidebar.py - Klika rzeczywiste ikony Fluidd w przeglądarce i symuluje restart przez WebSocket.
import json
import re
from urllib.parse import urlsplit


def check_sidebar(browser, url):
    context = browser.new_context(service_workers='block', viewport={'width': 1440, 'height': 950})
    try:
        page = context.new_page()
        page.add_init_script("sessionStorage.m300Loads = Number(sessionStorage.m300Loads || 0) + 1")
        connections = []
        methods = []

        def handle_socket(peer):
            def respond(message):
                packet = json.loads(message)
                method = packet['method']
                methods.append(method)
                if method == 'server.connection.identify':
                    connections.append(peer)
                server_info = dict(klippy_connected=True, klippy_state='ready', components=['history'],
                                   failed_components=[], registered_directories=[], warnings=[],
                                   missing_klippy_requirements=[], moonraker_version='0.10.0')
                responses = {
                    'server.connection.identify': {'connection_id': len(connections)},
                    'server.database.get_item': {'value': {}},
                    'server.database.post_item': {'value': {}},
                    'server.info': server_info,
                    'server.config': {'config': {}},
                    'printer.info': {'state': 'ready', 'software_version': 'v0.13.0'},
                    'printer.objects.list': {'objects': ['print_stats']},
                    'printer.objects.subscribe': {'eventtime': 1, 'status': {'print_stats': {'state': 'paused'}}},
                    'server.gcode_store': {'gcode_store': []},
                    'server.history.list': {'count': 0, 'jobs': []},
                    'server.history.totals': {'job_totals': {}, 'auxiliary_totals': []},
                    'server.files.list': [],
                }
                reply = {'jsonrpc': '2.0', 'id': packet['id']}
                if method in responses:
                    reply['result'] = responses[method]
                else:
                    reply['error'] = {'code': -32601, 'message': 'Unavailable in the offline sidebar test'}
                peer.send(json.dumps(reply))
            peer.on_message(respond)

        # The packaged app opens both a discovery probe and its regular RPC socket.
        page.route_web_socket('**/websocket', handle_socket)
        page.goto(url)
        def link(name):
            return page.locator(f'.nav-items a[href$="#/{name}"]')
        link('console').wait_for(state='visible')
        printer_query = urlsplit(page.url).query
        assert 'printer=' in printer_query

        def loaded(count):
            page.wait_for_function('n => Number(sessionStorage.m300Loads) === n', arg=count)
            link('console').wait_for(state='visible')
            assert urlsplit(page.url).query == printer_query

        # One stale lazy module while the old dashboard remains alive. The next
        # document must open the chosen route, keeping the selected printer.
        page.route(re.compile(r'/assets/Console-[^/]+\.js$'), lambda route: route.abort(), times=1)
        link('console').click()
        loaded(2)
        page.wait_for_url(re.compile(r'#/console$'))
        assert link('console').get_attribute('aria-current') == 'page'

        for count, name in ((3, 'settings'), (4, 'history')):
            # No WebSocket close; both restarts occur inside the RC24 cooldown.
            connections[-1].send(json.dumps({'jsonrpc': '2.0', 'method': 'notify_klippy_disconnected'}))
            connections[-1].send(json.dumps({'jsonrpc': '2.0', 'method': 'notify_klippy_ready'}))
            loaded(count)
            link(name).click()
            page.wait_for_url(re.compile(r'#/' + name + '$'))
            assert link(name).get_attribute('aria-current') == 'page'

        page.locator('[data-m300-panel-reload]').click()
        loaded(5)
        assert link('history').get_attribute('aria-current') == 'page'
        assert not any(method in ('printer.gcode.script', 'printer.restart', 'printer.firmware_restart',
                                  'printer.emergency_stop', 'printer.print.start', 'printer.print.resume')
                       for method in methods)
    finally:
        context.close()
