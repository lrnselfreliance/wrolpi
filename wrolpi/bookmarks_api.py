from dataclasses import dataclass
from http import HTTPStatus
from typing import Optional

from sanic import Blueprint, Request, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.bookmarks import get_bookmarks_config

bookmarks_bp = Blueprint('Bookmarks', '/api/bookmarks')


@dataclass
class BookmarkRequest:
    name: str
    url: str
    new_tab: bool = False
    parent_id: Optional[int] = None
    position: Optional[int] = None


@dataclass
class DirectoryRequest:
    name: str
    parent_id: Optional[int] = None
    position: Optional[int] = None


@dataclass
class NodeUpdateRequest:
    name: Optional[str] = None
    url: Optional[str] = None
    new_tab: Optional[bool] = None


@dataclass
class NodeMoveRequest:
    parent_id: Optional[int] = None
    position: Optional[int] = None


@bookmarks_bp.get('/')
@openapi.description('Get the bookmarks tree')
def get_bookmarks(_: Request):
    return json_response(dict(bookmarks=get_bookmarks_config().bookmarks), HTTPStatus.OK)


@bookmarks_bp.post('/')
@openapi.description('Add a bookmark, optionally inside a directory')
@validate(BookmarkRequest)
async def post_bookmark(_: Request, body: BookmarkRequest):
    node = get_bookmarks_config().add_bookmark(body.name, body.url, body.new_tab, body.parent_id, body.position)
    return json_response(dict(bookmark=node), HTTPStatus.CREATED)


@bookmarks_bp.post('/directory')
@openapi.description('Add a bookmark directory, optionally inside another directory')
@validate(DirectoryRequest)
async def post_directory(_: Request, body: DirectoryRequest):
    node = get_bookmarks_config().add_directory(body.name, body.parent_id, body.position)
    return json_response(dict(bookmark=node), HTTPStatus.CREATED)


@bookmarks_bp.put('/<node_id:int>')
@openapi.description('Rename a bookmark or directory; change a bookmark URL or new-tab setting')
@validate(NodeUpdateRequest)
async def put_node(_: Request, node_id: int, body: NodeUpdateRequest):
    node = get_bookmarks_config().update_node(node_id, body.name, body.url, body.new_tab)
    return json_response(dict(bookmark=node), HTTPStatus.OK)


@bookmarks_bp.post('/<node_id:int>/move')
@openapi.description('Move a bookmark or directory into a directory (null parent = top level) at a position')
@validate(NodeMoveRequest)
async def post_move(_: Request, node_id: int, body: NodeMoveRequest):
    node = get_bookmarks_config().move_node(node_id, body.parent_id, body.position)
    return json_response(dict(bookmark=node), HTTPStatus.OK)


@bookmarks_bp.delete('/<node_id:int>')
@openapi.description('Delete a bookmark, or a directory and its contents')
async def delete_node(_: Request, node_id: int):
    get_bookmarks_config().delete_node(node_id)
    return response.empty(HTTPStatus.NO_CONTENT)
