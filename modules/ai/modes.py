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
            ' Search the help documentation with search_help, read pages with get_help_doc, and answer'
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
            ' ALWAYS include the WROLPi link for every item you mention, exactly as the tools return it.'
            ' Never give external URLs.  When a search returns a large total, narrow the query instead'
            ' of paging.  If nothing matches, say so.'
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

# Suggestion chips shown by the Chat tab; small models do much better when the opening message
# matches what the mode's prompt was tuned for.
MODE_SUGGESTIONS = {
    'help': ['How do I download videos?', 'How do I add my own files?', 'What are Tags?'],
    'research': ['Find videos about canning', 'What do I have about gardening?', 'Summarize my newest archives'],
    'system': ['Why is my drive full?', 'Is everything running?', 'Why do downloads fail?'],
}
