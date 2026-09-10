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
            ' Search first with search_files, then read captions, page text, or entries with read_content'
            ' when the user wants detail.  The library list above has the exact channel, website, and'
            ' Zim names (spellings often differ): pass a channel or domain name to search_files directly.'
            ' To summarize a channel or browse everything of one kind, call search_files WITHOUT search_str'
            ' and with the channel, domain, or kind; that lists the newest items.'
            ' When a search finds nothing, do not give up: retry with fewer or different words, or drop the'
            ' filters.  When it offers matches, narrow with one of them.'
            ' ALWAYS include the WROLPi link for every item you mention, exactly as the tools return it.'
            ' Never give external URLs.  When a search returns a large total, narrow the query instead'
            ' of paging.'
        ),
        tools=(
            'search_files',
            'get_file',
            'read_content',
            'search_zims',
            'get_zim_entry',
            'get_inventory',
            'list_files',
            'read_file',
            'search_places',
        ),
    ),
    'system': dict(
        system_prompt=(
            f'{COMMON_PROMPT}'
            ' Your job is to troubleshoot the user\'s WROLPi.'
            ' You never know the current state of this system from memory or from example'
            ' conversations: EVERY answer about services, disks, or health starts with a fresh'
            ' get_system_status call.  Read a failing service\'s logs with get_service_logs;'
            ' check drives with list_disks.'
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
    # The example's content must be TRUE (from the real help docs): when a user asks about the
    # example's topic, a small model may answer straight from it without searching.
    'help': _example(
        dict(role='user', content='Why does my browser warn about the certificate?'),
        _tool_call('ex_help_1', 'search_help', '{"search_str": "certificate"}'),
        _tool_result('ex_help_1',
                     '{"results": [{"slug": "system/certificates", "title": "HTTPS Certificates",'
                     ' "link": "/system/certificates/",'
                     ' "snippet": "…WROLPi generates its own Root CA certificate…"}], "total": 1}'),
        _tool_call('ex_help_2', 'get_help_doc', '{"slug": "system/certificates"}'),
        _tool_result('ex_help_2',
                     '{"content": "# HTTPS Certificates\\nWROLPi is offline, so it cannot use a public'
                     ' certificate authority.  It generates its own Root CA certificate which you install'
                     ' once on each device that connects to it.", "next_offset": null, "total_chars": 205}'),
        dict(role='assistant', content='WROLPi is offline, so it cannot use a public certificate'
                                       ' authority; it signs its own certificate with a Root CA that you'
                                       ' install once on each device.  The HTTPS Certificates help page'
                                       ' explains how: /system/certificates/'),
    ),
    'research': _example(
        dict(role='user', content='Summarize the bakehouse channel'),
        _tool_call('ex_res_1', 'search_files', '{"channel": "Bakehouse"}'),
        _tool_result('ex_res_1',
                     '{"results": [{"id": 12, "kind": "video", "title": "Sourdough Basics",'
                     ' "link": "/videos/12", "channel": "Bakehouse", "duration": "15:00"}], "total": 1}'),
        dict(role='assistant', content='The Bakehouse channel has one video:\\n'
                                       '1. **Sourdough Basics** (/videos/12) — a 15 minute introduction'
                                       ' to sourdough baking.'),
    ),
    # No invented failures in the example: the model carries them into real diagnoses (it kept
    # investigating a fictional failed service the first version of this example described).
    'system': _example(
        dict(role='user', content='Is everything running?'),
        _tool_call('ex_sys_1', 'get_system_status', '{}'),
        _tool_result('ex_sys_1',
                     '{"version": "0.28", "wrol_mode": false, "services": [{"name": "wrolpi-api",'
                     ' "status": "running"}, {"name": "wrolpi-app", "status": "running"}], "errors": []}'),
        dict(role='assistant', content='The status shows both services (wrolpi-api, wrolpi-app)'
                                       ' running on version 0.28, with no errors reported.'),
    ),
}

# Suggestion chips shown by the Chat tab; small models do much better when the opening message
# matches what the mode's prompt was tuned for.
MODE_SUGGESTIONS = {
    'help': ['How do I download videos?', 'How do I add my own files?', 'What are Tags?'],
    'research': ['Find videos about canning', 'What do I have about gardening?', 'Summarize my newest archives'],
    'system': ['Why is my drive full?', 'Is everything running?', 'Why do downloads fail?'],
}
