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
        if gcmd.get_int('CHECK', 0):
            mesh = adapter.bedmesh.get_mesh()
            assert mesh.profile_name == 'm300_pads'
            matrix = mesh.get_mesh_matrix()
            assert len(matrix) == 61 and all(len(row) == 61 for row in matrix)
            params = mesh.get_mesh_params()
            assert (params['min_x'], params['min_y'], params['max_x'], params['max_y']) == (
                10., 19., 294., 300.)
            assert abs(mesh.calc_z(150, 158)) < .000001
            assert abs(mesh.calc_z(35, 44) - .3) < .001
            gcmd.respond_info('M300_CI_PAD_MESH profile load passed')
        else:
            assert adapter.points[1] == (244., 19.)
            assert adapter.points[11] == (130., 138.)
            adapter._publish('m300_pads', [.1] * 10 + [-.2] * 5 + [.1] * 10)
            assert adapter.bedmesh.get_mesh() is None


def load_config(config):
    return PadMeshFixture(config)
