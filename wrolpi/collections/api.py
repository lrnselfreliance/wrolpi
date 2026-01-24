"""
Collection API Endpoints

Unified REST API for all collection types (domains, channels, playlists, etc.).
"""
from http import HTTPStatus

from sanic import Request, Blueprint, response
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import wrol_mode_check
from wrolpi.schema import JSONErrorResponse
from . import lib, schema
from .errors import UnknownCollection

# Create blueprint
collection_bp = Blueprint('Collection', url_prefix='/api/collections')


@collection_bp.get('/')
@openapi.summary('Get all collections')
@openapi.parameter('kind', str, 'query', description='Filter by collection kind (e.g., domain, channel)',
                   required=False)
@openapi.response(HTTPStatus.OK, description="List of collections with metadata")
async def get_collections_endpoint(request: Request):
    """
    Get all collections, optionally filtered by kind.

    This unified endpoint works for all collection types. Use the 'kind' query parameter
    to filter by collection type (e.g., ?kind=domain or ?kind=channel).

    Examples:
        GET /api/collections - Get all collections
        GET /api/collections?kind=domain - Get only domain collections
        GET /api/collections?kind=channel - Get only channel collections

    Returns:
        - collections: List of collection objects
        - totals: Count of collections
        - metadata: UI metadata (columns, fields, routes, messages) if kind is specified
    """
    kind = request.args.get('kind')
    session = request.ctx.session

    collections = lib.get_collections(session, kind=kind)

    response_data = {
        'collections': collections,
        'totals': {'collections': len(collections)}
    }

    return json_response(response_data)


@collection_bp.get('/<collection_id:int>')
@openapi.summary('Get a single collection by ID')
@openapi.response(HTTPStatus.OK, description="Collection details with statistics")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_collection_endpoint(request: Request, collection_id: int):
    """
    Get details for a single collection including type-specific statistics.

    Returns collection metadata plus statistics specific to the collection type:
    - Domain collections: includes url_count and size
    - Channel collections: includes video_count and size
    - Other types: includes item_count and total_size
    """
    session = request.ctx.session
    try:
        collection_data = lib.get_collection_with_stats(session, collection_id)
        return json_response({'collection': collection_data})
    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)


@collection_bp.put('/<collection_id:int>')
@openapi.definition(
    summary='Update a collection',
    body=schema.CollectionUpdateRequest,
    validate=True,
)
@openapi.response(HTTPStatus.OK, description="Collection updated successfully")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def put_collection_endpoint(request: Request, collection_id: int, body: schema.CollectionUpdateRequest):
    """
    Update collection properties (directory, tag, description).

    This endpoint works for all collection types. You can update:
    - directory: Set or clear the collection's directory restriction
    - tag_name: Set or clear the collection's tag (requires directory)
    - description: Set or update the collection's description

    Note: To clear a field, pass an empty string. To leave unchanged, omit the field.
    """
    session = request.ctx.session
    try:
        collection = lib.update_collection(
            session,
            collection_id=collection_id,
            directory=body.directory,
            tag_name=body.tag_name,
            description=body.description
        )

        # Return updated collection data
        collection_data = lib.get_collection_with_stats(session, collection_id)
        return json_response({'collection': collection_data})

    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return json_response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)


@collection_bp.post('/<collection_id:int>/refresh')
@openapi.summary('Refresh files in collection directory')
@openapi.response(HTTPStatus.OK, description="Collection refresh started")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def refresh_collection_endpoint(_: Request, collection_id: int):
    """
    Queue a refresh for a collection's directory.

    This scans the collection's directory for new or modified files and updates
    the database accordingly. Only works for directory-restricted collections.

    The refresh happens asynchronously in the background.
    """
    try:
        lib.refresh_collection(collection_id, send_events=True)
        return json_response({'message': 'Collection refresh started'})

    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return json_response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)


@collection_bp.post('/<collection_id:int>/tag')
@openapi.definition(
    summary='Tag a collection and optionally move files',
    body=schema.CollectionTagRequest,
    validate=True,
)
@openapi.response(HTTPStatus.OK, schema.CollectionTagResponse, description="Collection tagged successfully")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def tag_collection_endpoint(request: Request, collection_id: int, body: schema.CollectionTagRequest):
    """
    Tag a collection and optionally move its files to a new directory.

    Tagging a collection:
    1. Creates or assigns the specified tag
    2. Optionally moves the collection to a new directory
    3. Updates the collection's metadata

    If no directory is specified, the collection must already have one.
    """
    session = request.ctx.session
    try:
        result = await lib.tag_collection(
            session,
            collection_id=collection_id,
            tag_name=body.tag_name,
            directory=body.directory
        )
        return json_response(result)

    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return json_response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)


@collection_bp.post('/<collection_id:int>/tag_info')
@openapi.definition(
    summary='Get tag information for a collection',
    body=schema.CollectionTagInfoRequest,
    validate=True,
)
@openapi.response(HTTPStatus.OK, schema.CollectionTagInfoResponse, description="Tag info retrieved successfully")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_tag_info_endpoint(request: Request, collection_id: int, body: schema.CollectionTagInfoRequest):
    """
    Get information about tagging a collection with a specific tag.

    Returns the suggested directory path and checks for conflicts with existing collections.
    Domain collections cannot share directories with other domain collections,
    but can share with channel collections.

    This is useful for showing users the suggested directory before they commit to tagging.
    """
    session = request.ctx.session
    try:
        tag_info = lib.get_tag_info(
            session,
            collection_id=collection_id,
            tag_name=body.tag_name
        )
        return json_response(tag_info)

    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)


@collection_bp.delete('/<collection_id:int>')
@openapi.definition(
    summary='Delete a collection',
)
@openapi.response(HTTPStatus.NO_CONTENT, description="Collection deleted successfully")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
async def delete_collection_endpoint(request: Request, collection_id: int):
    """
    Delete a collection and orphan its child items.

    For domain collections:
    - Orphans child Archives (sets collection_id to NULL)
    - Deletes the Collection record
    - Archives remain in the database but are no longer associated with a domain
    - Triggers domain config save
    """
    session = request.ctx.session
    try:
        collection = lib.delete_collection(session, collection_id=collection_id)
        from wrolpi.events import Events
        Events.send_deleted(f'Deleted {collection["kind"]} collection: {collection["name"]}')
        return response.raw('', HTTPStatus.NO_CONTENT)

    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)


@collection_bp.post('/search')
@openapi.definition(
    summary='Search collections',
    body=schema.CollectionSearchRequest,
    validate=True,
)
@openapi.response(HTTPStatus.OK, description="Search results")
async def search_collections_endpoint(request: Request, body: schema.CollectionSearchRequest):
    """
    Search collections by kind, tags, and name.

    Supports filtering by:
    - kind: Collection type (domain, channel, etc.)
    - tag_names: List of tag names (returns collections with any of these tags)
    - search_str: Search string for collection names (case-insensitive partial match)

    All filters are optional and can be combined.
    """
    session = request.ctx.session
    collections = lib.search_collections(
        session,
        kind=body.kind,
        tag_names=body.tag_names if body.tag_names else None,
        search_str=body.search_str
    )

    return json_response({
        'collections': collections,
        'totals': {'collections': len(collections)}
    })


@collection_bp.get('/<collection_id:int>/reorganize/preview')
@openapi.summary('Preview collection reorganization')
@openapi.response(HTTPStatus.OK, schema.ReorganizationPreviewResponse, description="Reorganization preview")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
async def preview_reorganization_endpoint(request: Request, collection_id: int):
    """
    Get preview with sample of files to be renamed.

    Returns a preview of what would happen if the collection is reorganized.
    This is useful for showing users what files would move before they commit.

    Returns:
        - collection_id: The collection ID
        - collection_name: The collection name
        - total_files: Total FileGroups in collection
        - files_needing_move: Count needing reorganization
        - sample_moves: ~10 example moves [{old_path, new_path}, ...]
        - new_file_format: The format template that will be applied
        - current_file_format: The format currently stored on collection
    """
    from wrolpi.collections.reorganize import get_reorganization_preview

    session = request.ctx.session
    try:
        # Use exact_count=True for individual collection preview to get accurate count
        preview = get_reorganization_preview(collection_id, session, exact_count=True)
        return json_response({
            'collection_id': preview.collection_id,
            'collection_name': preview.collection_name,
            'total_files': preview.total_files,
            'files_needing_move': preview.files_needing_move,
            'sample_moves': preview.sample_moves,
            'new_file_format': preview.new_file_format,
            'current_file_format': preview.current_file_format,
        })
    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)
    except ValueError as e:
        return json_response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)


@collection_bp.post('/<collection_id:int>/reorganize')
@openapi.summary('Execute collection reorganization')
@openapi.response(HTTPStatus.OK, schema.ReorganizationExecuteResponse, description="Reorganization started")
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def execute_reorganization_endpoint(request: Request, collection_id: int):
    """
    Execute reorganization.

    Moves files to match the current file_name_format configuration.
    The operation runs in the background via FileWorker.

    Returns:
        - job_id: For tracking progress via the status endpoint
        - message: Status message
    """
    from wrolpi.collections.reorganize import execute_reorganization

    session = request.ctx.session
    try:
        job_id = execute_reorganization(collection_id, session)
        if job_id:
            return json_response({
                'job_id': job_id,
                'message': 'Reorganization started'
            })
        else:
            return json_response({
                'job_id': '',
                'message': 'No files need reorganization'
            })
    except UnknownCollection as e:
        return json_response({'error': str(e)}, status=HTTPStatus.NOT_FOUND)
    except ValueError as e:
        return json_response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)


@collection_bp.get('/<collection_id:int>/reorganize/status/<job_id:str>')
@openapi.summary('Get reorganization status')
@openapi.response(HTTPStatus.OK, schema.ReorganizationStatusResponse, description="Reorganization status")
async def get_reorganization_status_endpoint(_: Request, collection_id: int, job_id: str):
    """
    Get status of in-flight reorganization.

    Returns:
        - status: 'pending' | 'running' | 'complete' | 'failed'
        - total: Total files to move
        - completed: Files moved so far
        - percent: Completion percentage
        - error: Error message if failed
    """
    from wrolpi.collections.reorganize import get_reorganization_status

    status = get_reorganization_status(job_id)
    return json_response(status)


# ============================================================================
# Batch Reorganization Endpoints
# ============================================================================


@collection_bp.get('/reorganize/channels')
@openapi.summary('List channels needing batch reorganization')
@openapi.response(HTTPStatus.OK, schema.BatchReorganizationListResponse,
                  description="List of channels needing reorganization")
async def list_channels_needing_reorganization_endpoint(request: Request):
    """
    List all channels that need reorganization because their file_name_format
    differs from the current config.

    Returns:
        - collections: List of channel info with sample moves
        - total_collections: Total count needing reorganization
        - total_files_needing_move: Sum of all files needing reorganization
        - new_file_format: The config format that will be applied
    """
    from wrolpi.collections.reorganize import get_collections_needing_reorganization

    session = request.ctx.session
    result = get_collections_needing_reorganization('channel', session)
    return json_response(result)


@collection_bp.get('/reorganize/domains')
@openapi.summary('List domains needing batch reorganization')
@openapi.response(HTTPStatus.OK, schema.BatchReorganizationListResponse,
                  description="List of domains needing reorganization")
async def list_domains_needing_reorganization_endpoint(request: Request):
    """
    List all domains that need reorganization because their file_name_format
    differs from the current config.

    Returns:
        - collections: List of domain info with sample moves
        - total_collections: Total count needing reorganization
        - total_files_needing_move: Sum of all files needing reorganization
        - new_file_format: The config format that will be applied
    """
    from wrolpi.collections.reorganize import get_collections_needing_reorganization

    session = request.ctx.session
    result = get_collections_needing_reorganization('domain', session)
    return json_response(result)


@collection_bp.post('/reorganize/channels')
@openapi.summary('Execute batch reorganization of all channels')
@openapi.response(HTTPStatus.OK, schema.BatchReorganizationExecuteResponse,
                  description="Batch reorganization started")
@wrol_mode_check
async def execute_batch_reorganization_channels_endpoint(request: Request):
    """
    Execute batch reorganization of all channels that need it.

    Processes channels sequentially. If any channel fails, the batch stops
    and reports which channel failed.

    Returns:
        - batch_job_id: For tracking progress via the batch status endpoint
        - message: Status message
        - collection_count: Number of channels to process
    """
    from wrolpi.collections.reorganize import execute_batch_reorganization

    session = request.ctx.session
    result = execute_batch_reorganization('channel', session)
    return json_response(result)


@collection_bp.post('/reorganize/domains')
@openapi.summary('Execute batch reorganization of all domains')
@openapi.response(HTTPStatus.OK, schema.BatchReorganizationExecuteResponse,
                  description="Batch reorganization started")
@wrol_mode_check
async def execute_batch_reorganization_domains_endpoint(request: Request):
    """
    Execute batch reorganization of all domains that need it.

    Processes domains sequentially. If any domain fails, the batch stops
    and reports which domain failed.

    Returns:
        - batch_job_id: For tracking progress via the batch status endpoint
        - message: Status message
        - collection_count: Number of domains to process
    """
    from wrolpi.collections.reorganize import execute_batch_reorganization

    session = request.ctx.session
    result = execute_batch_reorganization('domain', session)
    return json_response(result)


@collection_bp.get('/reorganize/batch/status/<batch_job_id:str>')
@openapi.summary('Get batch reorganization status')
@openapi.response(HTTPStatus.OK, schema.BatchReorganizationStatusResponse,
                  description="Batch reorganization status")
async def get_batch_reorganization_status_endpoint(_: Request, batch_job_id: str):
    """
    Get status of a batch reorganization job.

    Returns:
        - status: 'pending' | 'running' | 'complete' | 'failed' | 'unknown'
        - total_collections: Total collections in batch
        - completed_collections: Number completed so far
        - current_collection: Info about currently processing collection
        - overall_percent: Overall completion percentage
        - completed: List of completed collection info
        - failed_collection: Info about failed collection (if any)
        - error: Error message if failed
    """
    from wrolpi.collections.reorganize import get_batch_reorganization_status

    status = get_batch_reorganization_status(batch_job_id)
    return json_response(status)
