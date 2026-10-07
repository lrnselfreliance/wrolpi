from http import HTTPStatus

from sanic import Request, Blueprint, response
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import wrol_mode_check, logger
from wrolpi.errors import ValidationError
from . import lib, schema
from .models import Repository

repos_bp = Blueprint('Repos', '/api/repos')

logger = logger.getChild(__name__)


@repos_bp.get('/')
@openapi.definition(summary='List all git Repos')
async def get_repos(request: Request):
    repos = lib.get_repositories(request.ctx.session)
    return json_response(dict(repos=repos))


@repos_bp.post('/')
@openapi.definition(
    summary='Add a git Repo; it will be cloned, then kept up to date',
    body=schema.RepoCreateRequest,
    validate=True,
)
@wrol_mode_check
async def post_repo(request: Request, body: schema.RepoCreateRequest):
    lib.get_repos_config().check_imported()
    session = request.ctx.session
    repo = lib.create_repository(
        session,
        body.url,
        tag_name=body.tag_name or None,
        frequency=lib.DEFAULT_REPO_FREQUENCY if body.frequency is None else body.frequency,
        mode=body.mode or 'full',
        branch=body.branch or None,
        name=body.name or None,
        description=body.description or None,
        submodules=body.submodules,
        directory=(body.directory or '').strip() or None,
    )
    repo = Repository.find_by_id(session, repo.id, options=Repository.json_options())
    return json_response(dict(repo=repo.__json__()), status=HTTPStatus.CREATED)


@repos_bp.post('/import/inspect')
@openapi.definition(
    summary='What importing an existing git clone (in the media directory) as a Repo would do.  Changes nothing.',
    body=schema.RepoImportInspectRequest,
    validate=True,
)
async def post_inspect_import(request: Request, body: schema.RepoImportInspectRequest):
    info = lib.inspect_import(request.ctx.session, body.directory, body.name or None, body.tag_name or None,
                              body.url or None)
    return json_response(dict(inspection=info))


@repos_bp.post('/import')
@openapi.definition(
    summary='Import an existing git clone as a Repo.  It stays where it is, and becomes a mirror of its origin '
            '(local changes are discarded by its updates).',
    body=schema.RepoImportRequest,
    validate=True,
)
@wrol_mode_check
async def post_import(request: Request, body: schema.RepoImportRequest):
    lib.get_repos_config().check_imported()
    session = request.ctx.session
    repo = await lib.import_repository(
        session,
        body.directory,
        url=body.url or None,
        confirm=body.confirm,
        tag_name=body.tag_name or None,
        frequency=lib.DEFAULT_REPO_FREQUENCY if body.frequency is None else body.frequency,
        mode=body.mode or 'full',
        branch=body.branch or None,
        submodules=body.submodules,
        name=body.name or None,
        description=body.description or None,
    )
    repo = Repository.find_by_id(session, repo.id, options=Repository.json_options())
    return json_response(dict(repo=repo.__json__()), status=HTTPStatus.CREATED)


@repos_bp.post('/search')
@openapi.definition(
    summary='Search git Repos by their name and README, and/or by Tag',
    body=schema.RepoSearchRequest,
    validate=True,
)
async def post_search_repos(request: Request, body: schema.RepoSearchRequest):
    limit = min(max(body.limit, 1), 100)
    repos, total = lib.search_repos(request.ctx.session, body.search_str, body.tag_names, limit=limit,
                                    offset=max(body.offset, 0))
    return json_response(dict(repos=repos, totals=dict(repos=total)))


@repos_bp.get('/<repo_id:int>')
@openapi.definition(summary='Get a git Repo')
async def get_repo(request: Request, repo_id: int):
    repo = Repository.find_by_id(request.ctx.session, repo_id, options=Repository.json_options())
    return json_response(dict(repo=repo.__json__()))


@repos_bp.put('/<repo_id:int>')
@openapi.definition(
    summary="Change a git Repo's settings",
    body=schema.RepoUpdateRequest,
    validate=True,
)
@wrol_mode_check
async def put_repo(request: Request, repo_id: int, body: schema.RepoUpdateRequest):
    lib.get_repos_config().check_imported()
    session = request.ctx.session
    lib.update_repository(session, repo_id, description=body.description, frequency=body.frequency,
                          mode=body.mode, branch=body.branch, submodules=body.submodules)
    repo = Repository.find_by_id(session, repo_id, options=Repository.json_options())
    return json_response(dict(repo=repo.__json__()))


@repos_bp.delete('/<repo_id:int>')
@openapi.definition(summary='Delete a git Repo.  Its files are kept unless `delete_files=true`.')
@wrol_mode_check
async def delete_repo(request: Request, repo_id: int):
    lib.get_repos_config().check_imported()
    delete_files = request.args.get('delete_files', '').lower() in ('1', 'true', 'yes')
    await lib.delete_repository(request.ctx.session, repo_id, delete_files=delete_files)
    return response.empty()


@repos_bp.post('/<repo_id:int>/update')
@openapi.definition(summary='Update a git Repo now')
@wrol_mode_check
async def post_update_repo(request: Request, repo_id: int):
    session = request.ctx.session
    repo = Repository.find_by_id(session, repo_id)
    lib.request_repository_update(session, repo)
    session.commit()
    return response.empty(HTTPStatus.NO_CONTENT)


@repos_bp.get('/<repo_id:int>/tree')
@openapi.definition(summary="List a directory of a git Repo's files")
@openapi.parameter('path', str, 'query', description='Directory in the repo, relative to its root', required=False)
async def get_repo_tree(request: Request, repo_id: int):
    repo = Repository.find_by_id(request.ctx.session, repo_id)
    tree = lib.list_repo_tree(repo, request.args.get('path', ''))
    return json_response(tree)


@repos_bp.get('/<repo_id:int>/log')
@openapi.definition(summary="The commits of a git Repo's checked out branch, newest first")
@openapi.parameter('limit', int, 'query', description='At most 100', required=False)
@openapi.parameter('offset', int, 'query', required=False)
async def get_repo_log(request: Request, repo_id: int):
    repo = Repository.find_by_id(request.ctx.session, repo_id)
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        raise ValidationError('limit and offset must be numbers')
    log = await lib.get_repo_log(repo, limit=limit, offset=offset)
    return json_response(log)


@repos_bp.get('/<repo_id:int>/archive.zip')
@openapi.definition(summary="Download a ZIP of a git Repo's checked out files")
async def get_repo_archive(request: Request, repo_id: int):
    repo = Repository.find_by_id(request.ctx.session, repo_id)
    # Read everything from the database before the response starts; the request's session closes then.
    directory = lib.get_repo_root(repo)
    name = lib.repo_archive_name(repo)
    response = await request.respond(content_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="{name}.zip"',
    })
    await lib.stream_repo_archive(directory, name, response.send)
    await response.eof()
