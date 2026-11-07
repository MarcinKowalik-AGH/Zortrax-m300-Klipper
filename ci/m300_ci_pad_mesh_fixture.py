"""Synthetic pad heights for real Klippy FILEOUTPUT profile integration."""
class PadMeshFixture:
    def __init__(self, config):
        self.printer = config.get_printer()
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('ZORTRAX_CI_PAD_MESH', self.cmd_publish)

    def cmd_publish(self, gcmd):
        if not self.printer.lookup_object('mcu').is_fileoutput():
            raise gcmd.error('Pad mesh fixture requires FILEOUTPUT')
        adapter = self.printer.lookup_object('m300_pad_mesh')
        check = gcmd.get_int('CHECK', 0)
        if check == 8:
            from .m300_klipper_status import _BIT_PLANES
            from .m300_status_footer import klipper_footer
            status = self.printer.lookup_object('m300_klipper_status')
            for text in ('Bed mesh: Measuring point 11 of 25', 'Bed mesh: Measuring point 12 of 25'):
                self.printer.lookup_object('gcode').run_script_from_command('M117 '+text)
                wire = status.render(self.printer.get_reactor().monotonic())
                native = b''.join(bytes(page).translate(table)
                    for page in status.lcd_chip.vram for table in _BIT_PLANES)
                assert status.footer_text == text
                assert wire[:48*128] == native[:48*128]
                assert wire[48*128:] == klipper_footer(text)
                assert status.changed
            gcmd.respond_info('M300_CI_FOOTER native upper rows and full message passed')
            return
        if check == 5:
            expected=(
                (285.,15.),(260.,0.),(300.,0.),(300.,51.),(260.,51.),
                (15.,15.),(0.,0.),(43.,0.),(43.,51.),(0.,51.),
                (150.,150.),(125.,125.),(175.,125.),(175.,175.),(125.,175.),
                (285.,290.),(260.,262.),(300.,262.),(300.,305.),(260.,305.),
                (15.,290.),(0.,260.),(43.,260.),(43.,305.),(0.,305.))
            assert adapter.points == expected
            status=adapter.get_status(self.printer.get_reactor().monotonic())
            assert len(status['contact_regions']) == 5
            assert status['probe_points'] == [list(point) for point in expected]
            adapter._publish('m300_contact_pads',[.001*x+.002*y for x,y in expected])
            assert adapter.bedmesh.get_mesh() is None
            gcmd.respond_info('M300_CI_PAD_MESH contact rectangles passed')
        elif check == 6:
            mesh=adapter.bedmesh.get_mesh()
            assert mesh.profile_name == 'm300_contact_pads'
            assert abs(mesh.calc_z(0.,0.) + .466) < .000001
            assert abs(mesh.calc_z(260.,262.) - .318) < .000001
            assert abs(mesh.calc_z(300.,305.) - .444) < .000001
            gcmd.respond_info('M300_CI_PAD_MESH rectangle profile load passed')
        elif check == 7:
            assert adapter.points[16] == (260.,263.)
            assert adapter.geometry['rear_right_bounds'] == (260.,263.,300.,305.)
            assert adapter.bedmesh.get_mesh().profile_name == 'm300_contact_pads'
            gcmd.respond_info('M300_CI_PAD_MESH rectangle macro override passed')
        elif check == 3:
            assert adapter.geometry['edge_margin'] == adapter.travel_margin == 0.
            assert adapter.points[5:10] == ((15.,15.),(0.,0.),(45.,0.),(45.,45.),(0.,45.))
            assert adapter.points[:5] == ((285.,15.),(255.,0.),(300.,0.),(300.,45.),(255.,45.))
            assert adapter.points[10:15] == ((150.,150.),(125.,125.),(175.,125.),(175.,175.),(125.,175.))
            assert adapter.points[15:20] == ((285.,290.),(255.,260.),(300.,260.),(300.,305.),(255.,305.))
            assert adapter.points[20:25] == ((15.,290.),(0.,260.),(45.,260.),(45.,305.),(0.,305.))
            assert len(set(adapter.points)) == 25
            adapter._publish('m300_zero_pads',[.001*x+.002*y for x,y in adapter.points])
            assert adapter.bedmesh.get_mesh() is None
            gcmd.respond_info('M300_CI_PAD_MESH zero-margin geometry passed')
        elif check == 4:
            mesh=adapter.bedmesh.get_mesh()
            assert mesh.profile_name == 'm300_zero_pads'
            params=mesh.get_mesh_params()
            assert (params['min_x'],params['min_y'],params['max_x'],params['max_y']) == (0.,0.,300.,305.)
            assert abs(mesh.calc_z(0.,0.) + .466) < .000001
            assert abs(mesh.calc_z(45.,45.) + .331) < .000001
            assert abs(mesh.calc_z(300.,305.) - .444) < .000001
            gcmd.respond_info('M300_CI_PAD_MESH zero-margin profile load passed')
        elif check == 2:
            assert adapter.points[5] == (31., 30.)
            assert adapter.geometry['front_left_x'] == 31.
            assert adapter.bedmesh.get_mesh().profile_name == 'm300_pads'
            gcmd.respond_info('M300_CI_PAD_MESH macro preview passed')
        elif check:
            mesh = adapter.bedmesh.get_mesh()
            assert mesh.profile_name == 'm300_pads'
            matrix = mesh.get_mesh_matrix()
            assert len(matrix) == 61 and all(len(row) == 61 for row in matrix)
            params = mesh.get_mesh_params()
            assert (params['min_x'], params['min_y'], params['max_x'], params['max_y']) == (
                10., 10., 299., 304.)
            assert abs(mesh.calc_z(150, 158)) < .000001
            assert abs(mesh.calc_z(160, 160) - .0014) < .000001
            assert abs(mesh.calc_z(30, 30) - .2624) < .000001
            gcmd.respond_info('M300_CI_PAD_MESH profile load passed')
        else:
            assert adapter.points[1] == (270., 10.)
            assert adapter.points[11] == (140., 140.)
            heights = [.1] * 10 + [-.2] * 5 + [.1] * 10
            heights = [z + .0001*(x-160) + .0002*(y-160)
                       for (x, y), z in zip(adapter.points, heights)]
            adapter._publish('m300_pads', heights)
            assert adapter.bedmesh.get_mesh() is None


def load_config(config):
    return PadMeshFixture(config)
