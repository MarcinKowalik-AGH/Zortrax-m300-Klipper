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
        if check == 2:
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
                5., 5., 315., 315.)
            assert abs(mesh.calc_z(150, 158)) < .000001
            assert abs(mesh.calc_z(160, 160) - .0014) < .000001
            assert abs(mesh.calc_z(30, 30) - .2624) < .000001
            gcmd.respond_info('M300_CI_PAD_MESH profile load passed')
        else:
            assert adapter.points[1] == (265., 5.)
            assert adapter.points[11] == (140., 140.)
            heights = [.1] * 10 + [-.2] * 5 + [.1] * 10
            heights = [z + .0001*(x-160) + .0002*(y-160)
                       for (x, y), z in zip(adapter.points, heights)]
            adapter._publish('m300_pads', heights)
            assert adapter.bedmesh.get_mesh() is None


def load_config(config):
    return PadMeshFixture(config)
