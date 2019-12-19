from __future__ import annotations
from typing import List, Dict, Optional
from pyfluminus import utils, api
from pyfluminus.api_structs import Result, ErrorResult, EmptyResult, EmptyResultType
from pyfluminus.constants import ErrorTypes
import os
import requests
from bs4 import BeautifulSoup


class Module:

    teaching_perms = [
        "access_Full",
        "access_Create",
        "access_Update",
        "access_Delete",
        "access_Settings_Read",
        "access_Settings_Update",
    ]

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

    @classmethod
    def from_api(cls, api_data: Dict) -> Optional[Module]:
        """
        expect api_data to have the following fields: id, name, courseName, (access)
        """
        if not all(field in api_data for field in ["id", "name", "courseName"]):
            return None
        return Module(
            id=api_data["id"],
            code=api_data["name"],
            name=api_data["courseName"],
            teaching=any(
                api_data["access"].get(perm, False) for perm in cls.teaching_perms
            ),
            term=api_data["term"],
        )

    def announcements(self, auth: Dict, archived=False) -> Optional[List[Dict]]:
        """  Returns a list of announcements for a given module.
        The LumiNUS API provides 2 separate endpoints for archived and non-archived announcements. By default,
        announcements are archived after roughly 16 weeks (hence, the end of the
        semester) so most of the times, we should never need to access archived announcements.
        """
        result = api.get_announcements(auth, self.id, archived)
        if result.ok:
            return result.data
        return None

    def lessons(self, auth: Dict) -> Optional[List[Lesson]]:
        result = api.get_lessons(auth, self.id)
        if result.ok:
            return result.data
        else:
            return None

    def weblectures(self, auth: Dict) -> Optional[List[Weblecture]]:
        """Get all weblectures for this mod"""
        result = api.get_weblectures(auth, self.id)
        if result.ok:
            return result.data
        else:
            return None


class Lesson:
    def __init__(self, id: str, name: str, week: int, module_id: str):
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

    @classmethod
    def from_api(cls, api_data: Dict, module_id: str):
        return Lesson(
            id=api_data["id"],
            name=api_data["name"],
            week=int(api_data["navigationLabel"]),
            module_id=module_id,
        )

    def files(self):
        # TODO implement me
        """get files associated with that lesson plan"""
        uri = "lessonplan/Activity/?populate=TargetAncestor&ModuleID={}&LessonID={}".format(
            self.module_id, self.id
        )
        api_response = api.api(auth, uri)
        if "error" in api_response:
            return ErrorResult(ErrorTypes.Error, api_response["error"])

        if 'ok' in api_response and isinstance(api_response['ok'], list):
            return [File.from_lesson(data) for data in api_response['ok']]
        return None

    def __eq__(self, other):
        return (
            self.id == other.id
            and self.name == other.name
            and self.week == other.week
            and self.module_id == other.module_id
        )


class File:
    def __init__(
        self,
        id: str,
        name: str,
        directory: bool,
        children: Optional[List],
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
    def __eq(cls, f1, f2):
        if (
            f1.id == f2.id
            and f1.name == f2.name
            and f1.directory == f2.directory
            and f1.allow_upload == f2.allow_upload
            and f1.multimedia == f2.multimedia
        ):

            if f1.children is None or f2.children is None:
                return True
            if len(f1.children) == len(f2.children) == 0:
                return True

            if len(f1.children) == len(f2.children) and all(
                File.__eq(f1_child, f2_child)
                for f1_child, f2_child in zip(f1.children, f2.children)
            ):
                return True
        return False

    def __eq__(self, other):
        return File.__eq(self, other)

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
    def from_lesson(cls, api_data) -> Optional[File]:
        if api_data.get("target", None) is None or api_data["target"].get(
            "isResourceType", True
        ):
            return None

        target = api_data["target"]
        multimedia = "duration" in target
        return File(
            id=target["id"],
            name=utils.sanitise_filename(target["name"])
            + (".mp4" if multimedia else ""),
            children=[],
            allow_upload=False,
            multimedia=multimedia,
            directory=False,
        )

    @classmethod
    def get_children(cls, auth: Dict, id: str, allow_upload: bool) -> List[File]:
        directory_children = api.api(auth, "files/?ParentID={}".format(id))['ok']
        directory_files = api.api(
            auth,
            "files/{}/file{}".format(id, "?populate=Creator" if allow_upload else ""),
        )['ok']

        return [
            cls.parse_child(file_data, allow_upload)
            for file_data in directory_children["data"] + directory_files["data"]
        ]

    @classmethod
    def parse_child(cls, data: Dict, allow_upload: bool) -> File:
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
            response = api.api(auth, uri)['ok']
            return response.get("steamUrlPath", None)

        else:
            uri = "files/file/{}/downloadurl".format(self.id)
            response = api.api(auth, uri)['ok']
            return response.get("data", None)

    def download(self, auth: Dict, path: str, verbose: bool = False) -> Result:
        """Downloads file to location specified by `path`
        returns empty Result if successful, else returns ErrorResult(FileExists)
        """
        destination = os.path.join(path, self.name)
        url = self.get_download_url(auth)

        # NOTE it seems that requests handle multimedia downloads perfectly, do
        # not need to switch on if multimedia
        return utils.download(url, destination, verbose)

    def load_children(self, auth: Dict) -> EmptyResultType:
        if self.directory:
            children = File.get_children(auth, self.id, allow_upload=self.allow_upload)
            self.children = children
        else:
            self.children = []
        return EmptyResult()


class Weblecture:
    """
    Provides an abstraction over a weblecture in LumiNUS, and operations possible on them using
    LumiNUS API.

    Struct fields:
    * `:id` - id of the weblecture
    * `:name` - name of the weblecture
    * `:module_id` - the module_id to which the weblecture is from.
    """

    def __init__(self, id: str, name: str, module_id: str):
        self.id = id
        self.name = name
        self.module_id = module_id

    def __eq__(self, other):
        return (
            self.id == other.id
            and self.name == other.name
            and self.module_id == other.module_id
        )

    @classmethod
    def from_api(cls, api_data: Dict, module_id: str) -> Weblecture:
        return Weblecture(id=api_data["id"], name=api_data["name"], module_id=module_id)

    def download(self, auth: Dict, path: str, verbose: bool = False):
        """Downloads file to location specified by path, a requests sessions is used 
        as cookies are needed when downloading the mp4"""

        session = requests.Session()
        video_url = self.get_download_url(auth, session)
        destination = os.path.join(path, utils.sanitise_filename(self.name) + ".mp4")

        if video_url:
            return utils.download_w_session(session, video_url, destination, False)

    def get_download_url(self, auth: Dict, session) -> Optional[str]:
        """obtains download url for given weblecture"""
        # TODO migrate to api
        uri = "lti/Launch/panopto?context_id={}&resource_link_id={}".format(
            self.module_id, self.id
        )
        api_response = api.api(auth, uri)['ok']
        if "launchURL" in api_response and "dataItems" in api_response:
            launch_url, dataItems = api_response["launchURL"], api_response["dataItems"]

            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            dataItemsCombined = {item["key"]: item["value"] for item in dataItems}
            response = session.post(launch_url, headers=headers, data=dataItemsCombined)

            soup = BeautifulSoup(response.text, "html.parser")
            video = soup.find("meta", property="og:video")
            return video["content"]

        return None

