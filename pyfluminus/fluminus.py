from pyfluminus.structs import Module, File
from pyfluminus import api
from typing import Dict, List

def get_all_announcements(auth: Dict) -> List[Dict]:
    modules_res = api.modules(auth)
    if not modules_res.ok:
        print("Error: ", modules_res.error_msg)
    modules = modules_res.data
    result = []
    for module in modules:
        if module is None:
            print("Error parsing module data")
            continue
        result.append({
            "code": module.code,
            "name": module.name,
            "term": module.term,
            "announcements": module.announcements_full(auth)
        })
    return result

def get_announcements(auth: Dict, module_code: str) -> List[Dict]:
    modules_res = api.modules(auth)
    if not modules_res.ok:
        print("Error: ", modules_res.error_msg)
    modules = modules_res.data
    modules = list(filter(lambda mod: mod.code == module_code, modules))
    return modules[0].announcements_full(auth)

def get_links_for_module(auth: Dict, module: Module, verbose=False) -> Dict:
    """returns Folder containing nested folders, and files with download links
    Folder: {name: string, type: 'folder', children: List[Folder|File]}
    File: {name: string, type: 'file', link: string}
    Not to be confused with File from pyfluminus.structs
    """

    module_file = File.from_module(auth, module)
    return __traverse(auth, module_file, verbose)


def __traverse(auth: Dict, file: File, verbose=False) -> Dict:
    if not file.directory:
        return {"name": file.name, "type": "file", "link": file.get_download_url(auth)}
    if file.children is None:
        file.load_children(auth)
        if file.children is None:
            if verbose:
                print("Error loading children for file: {}".format(file.name))
            return {"name": file.name, "type": "folder", "children": []}
    return {
        "name": file.name,
        "type": "folder",
        "children": [__traverse(auth, children, verbose) for children in file.children],
    }
