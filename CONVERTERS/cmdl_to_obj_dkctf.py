import os
import sys
from cmdl_to_obj_core import convert_cmdl_to_obj
from windows_compat import is_macos_metadata_path


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print('Nutzung: python cmdl_to_obj_dkctf.py <eingabe.cmdl|eingabeordner> <ausgabeordner>')
        raise SystemExit(1)
    source = args[0]
    output_dir = args[1]
    os.makedirs(output_dir, exist_ok=True)
    if os.path.isdir(source):
        files = [os.path.join(source, name) for name in os.listdir(source) if not is_macos_metadata_path(name) and name.lower().endswith(('.cmdl', '.smdl', '.wmdl'))]
        files.sort()
    else:
        files = [source]
    if not files:
        print('Keine CMDL/SMDL/WMDL-Dateien gefunden.')
        raise SystemExit(1)
    failed = 0
    for path in files:
        try:
            result = convert_cmdl_to_obj(path, output_dir)
            print(f"OK  {os.path.basename(path)} -> {os.path.basename(result['output_obj_path'])} | Vertices: {result['vertex_count']} | Meshes: {result['mesh_count']} | Indices: {result['index_count_total']}")
        except Exception as exc:
            failed += 1
            print(f'FEHLER  {os.path.basename(path)} -> {exc}')
    if failed:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
