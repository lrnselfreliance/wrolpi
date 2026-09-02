"""Chat modes: a mode is a system prompt plus a tool allowlist, enforced server-side in the agent
loop — the model cannot opt out.  Tool names are the /api/ai blueprint's operationIds."""

COMMON_PROMPT = (
    'You are the WROLPi assistant, running locally on the user\'s own offline WROLPi server.'
    ' WROLPi is an off-grid digital library: videos, archived web pages, ebooks, Zim encyclopedias,'
    ' maps, and inventories.  You have no internet access.'
    ' Answer briefly and plainly.  Use the provided tools to find real information before answering;'
    ' never invent library content or system state.'
)

MODES = {
    'help': dict(
        system_prompt=(
            f'{COMMON_PROMPT}'
            ' Your job is to teach the user how to use WROLPi.'
            ' You do NOT know how WROLPi works from memory: before answering ANY question, you MUST'
            ' first call search_help, then read the matching page with get_help_doc, and answer only'
            ' from what the docs actually say.  Always include the link of every help page you used.'
            ' If the docs do not cover the question, say so.'
        ),
        tools=(
            'search_help',
            'get_help_doc',
            'get_system_status',
        ),
    ),
    'research': dict(
        system_prompt=(
            f'{COMMON_PROMPT}'
            ' Your job is to be the librarian: find and summarize content from the user\'s library.'
            ' Search first, then read captions, page text, or entries when the user wants detail.'
            ' When the user asks about a channel, website, or their whole library, call'
            ' list_collections first to learn the exact names (spellings often differ).'
            ' list_collections only gives names — it never tells you what content exists.  You have'
            ' not summarized a channel until you have called search_videos with its channel_id (and'
            ' NO search_str) and read the resulting titles.'
            ' To browse everything of one kind (e.g. "summarize my archives"), call the search tool'
            ' WITHOUT search_str — that lists the newest items.'
            ' When a search finds nothing, do not give up: retry with fewer or different words, or'
            ' browse with list_collections.'
            ' ALWAYS include the WROLPi link for every item you mention, exactly as the tools return it.'
            ' Never give external URLs.  When a search returns a large total, narrow the query instead'
            ' of paging.'
        ),
        tools=(
            'search_all',
            'search_videos',
            'get_video',
            'get_video_captions',
            'search_archives',
            'get_archive_text',
            'search_docs',
            'get_doc',
            'list_zims',
            'search_zims',
            'get_zim_entry',
            'list_collections',
            'list_inventories',
            'get_inventory',
            'read_file',
        ),
    ),
    'system': dict(
        system_prompt=(
            f'{COMMON_PROMPT}'
            ' Your job is to troubleshoot the user\'s WROLPi.'
            ' Start every diagnosis with get_system_status; read a failing service\'s logs with'
            ' get_service_logs; check drives with list_disks.'
            ' You CANNOT execute commands or change anything — you can only read.'
            ' Only suggest commands that appear in the help documentation: find them with search_help,'
            ' quote them exactly, and include the help page link.'
        ),
        tools=(
            'get_system_status',
            'list_services',
            'get_service_logs',
            'list_disks',
            'search_help',
            'get_help_doc',
        ),
    ),
}


def _example(*messages) -> list:
    """A compact worked exchange (user -> tool call -> tool result -> answer) prepended to every
    conversation.  Small models imitate far better than they obey; one example per mode is what
    stops them answering from memory or quitting after the first tool call."""
    return list(messages)


def _tool_call(call_id: str, name: str, arguments: str) -> dict:
    return dict(role='assistant', content=None, tool_calls=[
        dict(id=call_id, type='function', function=dict(name=name, arguments=arguments))])


def _tool_result(call_id: str, content: str) -> dict:
    return dict(role='tool', tool_call_id=call_id, content=content)


MODE_EXAMPLES = {
    'help': _example(
        dict(role='user', content='How do I tag a video?'),
        _tool_call('ex_help_1', 'search_help', '{"search_str": "tag video"}'),
        _tool_result('ex_help_1',
                     '{"results": [{"slug": "system/tags", "title": "Tags", "link": "/system/tags/",'
                     ' "snippet": "…Tags group related content across the library…"}], "total": 1}'),
        _tool_call('ex_help_2', 'get_help_doc', '{"slug": "system/tags"}'),
        _tool_result('ex_help_2',
                     '{"content": "# Tags\\nOpen any video and press the tag button to add a tag.",'
                     ' "next_offset": null, "total_chars": 62}'),
        dict(role='assistant', content='Open any video and press the tag button to add a tag.'
                                       '  See the Tags help page: /system/tags/'),
    ),
    'research': _example(
        dict(role='user', content='Summarize the bakehouse channel'),
        _tool_call('ex_res_1', 'list_collections', '{"kind": "channel"}'),
        _tool_result('ex_res_1',
                     '{"results": [{"id": 7, "name": "Bakehouse", "kind": "channel",'
                     ' "link": "/videos/channel/7/video"}], "total": 1}'),
        _tool_call('ex_res_2', 'search_videos', '{"channel_id": 7}'),
        _tool_result('ex_res_2',
                     '{"results": [{"id": 12, "kind": "video", "title": "Sourdough Basics",'
                     ' "link": "/videos/12", "channel": "Bakehouse", "duration": 900}], "total": 1}'),
        dict(role='assistant', content='The Bakehouse channel (/videos/channel/7/video) has one video:'
                                       ' Sourdough Basics (/videos/12), a 15 minute introduction to'
                                       ' sourdough baking.'),
    ),
    'system': _example(
        dict(role='user', content='Is everything running?'),
        _tool_call('ex_sys_1', 'get_system_status', '{}'),
        _tool_result('ex_sys_1',
                     '{"version": "0.28", "wrol_mode": false, "services": [{"name": "wrolpi-api",'
                     ' "status": "running"}, {"name": "wrolpi-kiwix", "status": "failed"}], "errors": []}'),
        dict(role='assistant', content='Almost: wrolpi-kiwix has failed; everything else is running.'
                                       '  I can read its logs to find out why.'),
    ),
}

# Suggestion chips shown by the Chat tab; small models do much better when the opening message
# matches what the mode's prompt was tuned for.
MODE_SUGGESTIONS = {
    'help': ['How do I download videos?', 'How do I add my own files?', 'What are Tags?'],
    'research': ['Find videos about canning', 'What do I have about gardening?', 'Summarize my newest archives'],
    'system': ['Why is my drive full?', 'Is everything running?', 'Why do downloads fail?'],
}
