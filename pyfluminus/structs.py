from __future__ import annotations
from typing import List, Dict
from pyfluminus import utils
from pyfluminus.api import api, Result, ErrorResult
import os


class Module:
    def __init__(self, id: str, code: str, name: str, teaching: bool, term: str):
        """
        * `:id` - id of the module in the LumiNUS API
        * `:code` - code of the module, e.g. `"CS1101S"`
        * `:name` - name of the module, e.g. `"Programming Methodology"`
        * `:teaching?` - `true` if the user is teaching the module, `false` if the user is taking the module
        * `:term` - a string identifier used by the LumiNUS API to uniquely identify a term (semester), e.g. `"1820"`
        is invalid
        """
        self.id = id
        self.code = code
        self.name = name
        self.teaching = teaching
        self.term = term

    def __eq__(self, other):
        return (
            self.id == other.id
            and self.code == other.code
            and self.name == other.name
            and self.teaching == other.teaching
            and self.term == other.term
        )


class Lesson:
    def __init__(self, id: str, name: str, week: str, module_id: str):
        """
        Provides an abstraction over a lesson plan in LumiNUS, and operations possible on them using
        LumiNUS API.

        Struct fields:
        * `:id` - id of the lesson plan
        * `:name` - name of the lesson plan
        * `:week` - which week the lesson plan is for
        * `:module_id` - the module id to which the lesson plan is from.
        """
        self.id = id
        self.name = name
        self.week = week
        self.module_id = module_id


class File:
    def __init__(
        self,
        id: str,
        name: str,
        directory: bool,
        children: List,
        allow_upload: bool,
        multimedia: bool,
    ):
        """
        Provides an abstraction over a file/directory in LumiNUS, and operations possible on them using
        LumiNUS API.

        Struct fields:
        * `:id` - id of the file
        * `:name` - the name of the file
        * `:directory?` - whether this file is a directory
        * `:children` - `nil` indicated the need to fetch, otherwise it contains a list of its children.
        if `directory?` is `false`, then this field contains an empty list.
        * `:allow_upload?` - whether this is a student submission folder.
        * `:multimedia?` - whether this is a multimedia file.
        """
        self.id = id
        self.name = name
        self.directory = directory
        self.children = children
        self.allow_upload = allow_upload
        self.multimedia = multimedia

    def __str__(self):
        return f"id: {self.id}, name: {self.name}, directory: {self.directory}, children: {self.children}, allow_upload: {self.allow_upload}, multimedia: {self.multimedia}"

    @classmethod
    def from_module(cls, auth: Dict, module: Module) -> File:
        return File(
            id=module.id,
            name=utils.sanitise_filename(module.code),
            directory=True,
            children=cls.get_children(auth, module.id, allow_upload=False),
            allow_upload=False,
            multimedia=False,
        )

    @classmethod
    def get_children(cls, auth: Dict, id: str, allow_upload: bool) -> List[File]:
        directory_children = api(auth, "files/?ParentID={}".format(id))
        directory_files = api(
            auth,
            "files/{}/file{}".format(id, "?populate=Creator" if allow_upload else ""),
        )
        # print(directory_children)
        # print(directory_files)

        return [
            cls.parse_child(file_data, allow_upload)
            for file_data in directory_children["data"] + directory_files["data"]
        ]

    @classmethod
    def parse_child(cls, data: Dict, allow_upload: bool) -> File:
        # TODO handle add creator name
        is_directory = isinstance(data.get("access", None), dict)
        return File(
            id=data["id"],
            name=utils.sanitise_filename(
                "{}{}".format(
                    data["creatorName"] + " - " if allow_upload else "", data["name"]
                )
            ),
            directory=is_directory,
            children=None
            if is_directory
            else [],  # NOTE [] indicates that there is no children, None means unknown (lazy)
            allow_upload=data.get("allowUpload", False),
            multimedia=False,
        )

    def get_download_url(self, auth: Dict):
        if self.multimedia:
            uri = "multimedia/media/{}".format(self.id)
            response = api(auth, uri)
            return response.get("steamUrlPath", None)

        else:
            uri = "files/file/{}/downloadurl".format(self.id)
            response = api(auth, uri)
            return response.get("data", None)

    def download(self, auth: Dict, path: str, verbose: bool = False) -> Result:
        """Downloads file to location specified by `path`
        TODO handle case where file is already there, currently, just do nothing
        """
        destination = os.path.join(path, self.name)
        url = self.get_download_url(auth)

        if self.multimedia:
            return utils.download_multimedia(url, destination, verbose)
        else:
            return utils.download(url, destination, verbose)

    def load_children(self, auth: Dict) -> Result:
        # TODO handle get_children returning result
        if self.directory:
            children = File.get_children(auth, self.id, allow_upload=self.allow_upload)
            self.children = children
        else:
            self.children = []
        return Result()

