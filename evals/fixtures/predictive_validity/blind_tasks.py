from __future__ import annotations

# Blind (anti-tautology) tasks for the predictive-validity study.
#
# BUG THIS FIXES: agentgauge.tasks.generate_tasks() builds task text as
# f"Call '{tool.name}': {tool.description}" — it literally quotes the gold tool name
# inside the task the agent sees. Using generate_tasks() as ground truth for "did the
# agent succeed" makes success trivial (copy the quoted name back) regardless of
# description quality, producing a zero-variance ground truth. This module is the fix:
# every task below expresses user intent only — never the gold tool's name, never a
# required enum/param value verbatim — following the repo's established convention in
# evals/fixtures/t17_tasks.py, ty_tasks.py, ty2_tasks.py, and t18_catalog.py.
#
# BLIND_TASKS is keyed by ToolSetEntry.name (see manifest.py) and used as ground-truth
# task input for the predictive-validity data collection run instead of generate_tasks().
#
# Sourcing per entry (see task report for full rationale):
#   - confusable_server / _oracle       -> reuse t17_tasks.TASKS verbatim (16 tools, 32 tasks)
#   - grounded_server / _oracle         -> transcribed from grounded_server.py's own
#                                          pre-registered 10-task header comment (5 tools)
#   - call_constraints_server / _oracle -> reuse ty_tasks.TASKS verbatim (8 tools, 32 tasks)
#   - call_constraints_v2_server/_oracle-> reuse ty2_tasks.TASKS verbatim (6 tools, 30 tasks)
#   - t18_* (4 arms)                    -> t18_catalog.TASKS filtered to the 12-tool
#                                          data_fetch+notify subset, topped up with new
#                                          hand-authored tasks so every one of the 12
#                                          tools gets >=2 tasks (the catalog's own TASKS
#                                          list only covers 4-of-6 tools per family with
#                                          1 task each; 4 of our 12 filtered tools had
#                                          ZERO catalog tasks before the top-up)
#   - echo_server, mediocre_server,     -> new hand-authored tasks, grounded in each
#     call_constraints_server, arxiv/   server's real list_tools()/call_tool() bodies
#     linkedin/jupyter mirrors            (read directly, not guessed)
from agentgauge.tasks import Task
from evals.fixtures.p2a_internal_proxy_catalog import TASKS as _P2A_TASKS
from evals.fixtures.q3_catalog import TASKS as _Q3_CATALOG_TASKS
from evals.fixtures.q6_catalog import TASKS as _Q6_CATALOG_TASKS
from evals.fixtures.rw1_github_catalog import TASKS as _RW1_TASKS
from evals.fixtures.rw2_aws_iam_catalog import TASKS as _RW2_TASKS
from evals.fixtures.t17_tasks import TASKS as _T17_TASKS
from evals.fixtures.t18_catalog import FAMILIES as _T18_FAMILIES
from evals.fixtures.t18_catalog import TASKS as _T18_CATALOG_TASKS
from evals.fixtures.ty2_tasks import TASKS as _TY2_TASKS
from evals.fixtures.ty_tasks import TASKS as _TY_TASKS

# ── echo_server (examples/echo_server.py) ───────────────────────────────────────
# 4 tools: echo (message->message), add (a+b->sum), mystery (x,y untyped, always
# returns "???"), greet (name+prefix->"{prefix}, {name}!"). mystery/greet have empty
# descriptions and untyped params by design (schema-completeness floor fixture) —
# tasks describe the runtime behavior read from call_tool(), not guessed intent.
# "add" is avoided as a literal token (it's both the tool name and the generic English
# verb) by phrasing arithmetic requests with "plus"/"sum of" instead.
ECHO_SERVER_TASKS: list[Task] = [
    Task(
        "echo", "Send back the exact text 'system check 42' unchanged so I can confirm round-trip"
    ),
    Task("echo", "Repeat this message back to me exactly as given: 'connectivity probe alpha'"),
    Task("add", "What is 17 plus 26?"),
    Task("add", "Give me the sum of 84 and 39"),
    Task(
        "mystery",
        "Send two arbitrary probe values into the server's undocumented diagnostic "
        "endpoint and see what response comes back",
    ),
    Task(
        "mystery",
        "Try feeding two test numbers into the unlabeled experimental endpoint to "
        "observe its output",
    ),
    Task("greet", "Produce a friendly welcome message for a person named 'Priya'"),
    Task(
        "greet",
        "Generate a custom salutation using 'Hey there' as the opening phrase for a "
        "user named 'Sam'",
    ),
]

# ── confusable_server / confusable_server_oracle ────────────────────────────────
# 16 tool names confirmed identical to t17_tasks.py's 16 (both are the T17 fixture's
# own arm A / arm B server pair). Reused verbatim — same 32 tasks work for both arms
# since only tool *descriptions* differ between arms, never names or schemas.
CONFUSABLE_SERVER_TASKS: list[Task] = list(_T17_TASKS)

# ── grounded_server / grounded_server_oracle ────────────────────────────────────
# 5 tools confirmed identical between arms (transform_scale, transform_normalize,
# transform_clip, transform_round, transform_log). Transcribed verbatim from
# grounded_server.py's own pre-registered "10 tasks, 2 per tool" header comment
# (lines ~27-37) — these were already phrased as natural user intent with no tool
# name or oracle-description vocabulary echoed.
GROUNDED_SERVER_TASKS: list[Task] = [
    Task("transform_scale", "Multiply 4.0 by 2.5 and add 0.5 to the result"),
    Task("transform_scale", "Apply a 50% amplitude reduction and subtract 3.0 from value 8.0"),
    Task("transform_normalize", "Express 7.0 as a fraction of the range [0, 10]"),
    Task(
        "transform_normalize",
        "Rescale 25.0 to fit between 0 and 1, given original bounds 0 and 50",
    ),
    Task("transform_clip", "Ensure value 105 does not exceed 100 and is at least 0"),
    Task("transform_clip", "Cap measurement -2.5 so it stays within the valid range [0, 50]"),
    Task("transform_round", "Express 3.14159265 to 4 decimal places"),
    Task("transform_round", "Reduce precision of 99.9999 to at most 2 decimal places"),
    Task("transform_log", "What is ln(10.0)?"),
    Task("transform_log", "Compute log base 2 of 8.0"),
]

# ── mediocre_server (examples/mediocre_server.py) ───────────────────────────────
# 5 tools: put_x(sid,key,val,ts), get_a(sid,key=record id), get_b(sid,key=agg fn in
# {sum,min,max,avg}), del_a(sid,key=record id), del_b(sid,key=delete mode in
# {hard,soft}). get_a/get_b and del_a/del_b share IDENTICAL param names by design
# (T16 run #4 fixture — only descriptions/schema can distinguish them). Tasks below
# never say "sum"/"min"/"max"/"avg"/"hard"/"soft" literally — the agent must map
# intent to the correct enum value using the schema, not the task text.
MEDIOCRE_SERVER_TASKS: list[Task] = [
    Task(
        "put_x",
        "Store a new sensor measurement of 23.5 recorded at unix time 1700000000 "
        "under record key 'temp-01' in session 42",
    ),
    Task(
        "put_x",
        "Save a reading of 88.2 for session 7, tagging it with key 'pressure-03' and "
        "recording when it was captured",
    ),
    Task(
        "get_a",
        "Look up the individual measurement stored under record key 'temp-01' in session 42",
    ),
    Task(
        "get_a",
        "Retrieve the exact reading that was saved earlier under key 'pressure-03' for session 7",
    ),
    Task("get_b", "Get the total of every measurement recorded in session 42"),  # sum
    Task("get_b", "Find the smallest measurement value recorded across session 7"),  # min
    Task("get_b", "Find the largest reading recorded in session 42"),  # max
    Task("get_b", "Get the average value across all measurements recorded in session 7"),  # avg
    Task(
        "del_a",
        "Remove the single stored record with key 'temp-01' from session 42",
    ),
    Task(
        "del_a",
        "Delete just the entry under key 'pressure-03' in session 7, leaving other "
        "records untouched",
    ),
    Task(
        "del_b",
        "Erase all of session 42's records completely, with no way to recover them afterward",
    ),  # hard
    Task(
        "del_b",
        "Deactivate session 7's records but keep them recoverable in case they're needed later",
    ),  # soft
]

# ── call_constraints_server / call_constraints_server_oracle ───────────────────
# 8 tool names (ping_server, get_server_info, list_channels, reset_state,
# set_acquisition_mode, configure_output_codec, schedule_maintenance,
# set_channel_routing) confirmed identical to ty_tasks.py's own fixture pair —
# reused verbatim (32 tasks; hard-tool tasks already respect ANTI-TAUTOLOGY RULE
# per that module's own header).
CALL_CONSTRAINTS_SERVER_TASKS: list[Task] = list(_TY_TASKS)

# ── call_constraints_v2_server / call_constraints_v2_server_oracle ─────────────
# 6 tool names (register_channel, log_fault, set_output_encoding, set_trigger_mode,
# set_debounce_delay, configure_watchdog) confirmed identical to ty2_tasks.py's own
# fixture pair — reused verbatim (30 tasks; ANTI-TAUTOLOGY RULE enforced by that
# module's own header — no enum values, format patterns, or unit names in task text).
CALL_CONSTRAINTS_V2_SERVER_TASKS: list[Task] = list(_TY2_TASKS)

# ── T18 family (t18_vague_server, t18_fixer_server, t18_q2b_server, t18_oracle_server) ──
# All 4 arms are filtered to the same 12-tool subset (data_fetch + notify families,
# per manifest.py's _T18_FAMILY_SUBSET — recomputed here identically; keep in sync).
# t18_catalog.TASKS is NOT 1:1 tool coverage: it has only 40 tasks for the 60-tool
# catalog (4 per family, 1 task for 4-of-6 tools per family). Filtering it to our
# 12-tool subset yields tasks for only 8 of the 12 tools (get_record, fetch_record,
# read_entry, load_item, notify_user, alert_contact, send_notification, trigger_event),
# each with exactly ONE task — a 1-shot coin flip, and retrieve_row, pull_document,
# broadcast_message, ping_service have ZERO catalog tasks at all. _T18_GAP_TASKS below
# adds a 2nd task to each of the 8 covered tools and 2 new tasks each for the 4
# uncovered tools, bringing every one of the 12 tools to >=2 tasks. All tasks avoid
# family-distinguishing oracle vocabulary from ARM_B_DESCRIPTIONS (e.g. "primary key",
# "REST API", "in-app inbox") the same way the catalog's own pre-registered tasks do.
_T18_FAMILY_SUBSET: list[str] = _T18_FAMILIES["data_fetch"] + _T18_FAMILIES["notify"]

_T18_GAP_TASKS: list[Task] = [
    # data_fetch — 2nd task for the 4 tools the catalog already covers
    Task(
        "get_record",
        "The billing service needs account ACCT-4471's data fetched straight from "
        "the primary datastore using its unique key",
    ),
    Task(
        "fetch_record",
        "Pull the shipping status for order #55219 by calling the courier partner's remote web API",
    ),
    Task(
        "read_entry",
        "The deployment script needs the feature-flags entry from the local config "
        "file at /opt/app/flags.yaml",
    ),
    Task(
        "load_item",
        "The recommendation engine needs the last-viewed items list for this browser "
        "session, served instantly without a database round-trip",
    ),
    # data_fetch — new tasks for the 2 tools the catalog never covers
    Task(
        "retrieve_row",
        "Pull the customer row from the accounts SQL table where email equals 'j.doe@example.com'",
    ),
    Task(
        "retrieve_row",
        "Get the shipment row from the logistics table whose tracking_number is 'TRK-88213'",
    ),
    Task(
        "pull_document",
        "Fetch the user profile document stored in the document-store collection "
        "for user_id 'u-7734'",
    ),
    Task(
        "pull_document",
        "Retrieve the product listing document from the catalog collection by its "
        "document id 'doc-2291'",
    ),
    # notify — 2nd task for the 4 tools the catalog already covers
    Task(
        "notify_user",
        "Show a reminder banner inside the app for the user with account number "
        "8834 about their expiring trial",
    ),
    Task(
        "alert_contact",
        "Send an urgent text alert to the on-site technician's registered phone "
        "number about the outage",
    ),
    Task(
        "send_notification",
        "Push a mobile alert to the user's phone letting them know their ride has arrived",
    ),
    Task(
        "trigger_event",
        "Record the 'payment_failed' occurrence in the internal event log so other "
        "services can react",
    ),
    # notify — new tasks for the 2 tools the catalog never covers
    Task(
        "broadcast_message",
        "Send the same announcement simultaneously to everyone currently subscribed "
        "to the #incidents channel",
    ),
    Task(
        "broadcast_message",
        "Blast a maintenance-window notice out to every subscriber of the "
        "status-updates channel at once",
    ),
    Task(
        "ping_service",
        "Check whether the billing microservice's health endpoint is currently responding",
    ),
    Task(
        "ping_service",
        "Verify that the downstream inventory service is up and reachable right now",
    ),
]

T18_SUBSET_TASKS: list[Task] = [
    t for t in _T18_CATALOG_TASKS if t.tool_name in _T18_FAMILY_SUBSET
] + _T18_GAP_TASKS

# ── exp1_datalayer_jupyter_mcp_server_mirror / _oracle ──────────────────────────
# 17 tool names read from DOCSTRINGS in exp1_datalayer_jupyter_mcp_server_mirror.py;
# confirmed identical in the _oracle variant (same DOCSTRINGS keys, different values).
# call_tool() is a generic stub (json.dumps({"stub": True, ...})) — tasks describe
# plausible real-world intent matching each tool's real public docstring; the stub
# accepts any call regardless of whether it would "really" work.
EXP1_JUPYTER_MIRROR_TASKS: list[Task] = [
    Task(
        "list_files",
        "Show me every file and folder inside the Jupyter server's workspace, "
        "including nested subfolders",
    ),
    Task(
        "list_files",
        "I need to locate a specific dataset file somewhere in the Jupyter server's "
        "directory tree — show the full structure",
    ),
    Task(
        "list_kernels",
        "Show me all the kernel sessions currently running or available on this Jupyter server",
    ),
    Task(
        "list_kernels",
        "I need to see which kernels are active right now, along with their IDs "
        "and connection details",
    ),
    Task(
        "use_notebook",
        "Set 'analysis.ipynb' at path /work/analysis.ipynb as the active notebook "
        "for the cell operations I'm about to do",
    ),
    Task(
        "use_notebook",
        "Switch my working context over to the notebook called 'report_gen' so I "
        "can start editing its cells",
    ),
    Task(
        "list_notebooks",
        "Which notebooks have I already activated and worked with in this session?",
    ),
    Task(
        "list_notebooks",
        "Give me the names of every notebook I've opened for editing so far",
    ),
    Task(
        "restart_notebook",
        "The kernel for 'training_run.ipynb' seems stuck — restart it",
    ),
    Task(
        "restart_notebook",
        "Reboot the kernel backing the 'etl_pipeline' notebook so I can start fresh",
    ),
    Task(
        "unuse_notebook",
        "I'm done working with 'scratch.ipynb' for now — release it and free up its resources",
    ),
    Task(
        "unuse_notebook",
        "Deactivate the 'old_experiment' notebook I was using so it stops holding onto memory",
    ),
    Task(
        "read_notebook",
        "Give me a quick overview of every cell in the currently active notebook so "
        "I can find the one I need to edit",
    ),
    Task(
        "read_notebook",
        "Show me the detailed contents, outputs and execution counts of each cell "
        "in the currently open notebook for debugging",
    ),
    Task(
        "insert_cell",
        "Add a new markdown cell at position 3 in the currently active notebook "
        "with a section header",
    ),
    Task(
        "insert_cell",
        "Insert a fresh empty code cell right after the second cell in the current notebook",
    ),
    Task(
        "overwrite_cell_source",
        "Completely rewrite cell 5 in the active notebook to import pandas and "
        "load a CSV instead of what's there now",
    ),
    Task(
        "overwrite_cell_source",
        "Replace the whole contents of cell 2 with a fresh implementation of the training loop",
    ),
    Task(
        "edit_cell_source",
        "In cell 4 of the active notebook, change every occurrence of the variable "
        "name 'df_old' to 'df_new' without touching anything else",
    ),
    Task(
        "edit_cell_source",
        "Find the string 'learning_rate=0.01' in cell 7 and swap it for "
        "'learning_rate=0.001', leaving the rest of the cell untouched",
    ),
    Task(
        "execute_cell",
        "Run cell 6 in the currently active notebook and show me its output",
    ),
    Task(
        "execute_cell",
        "Execute the cell at index 3 with a generous timeout since it trains a model",
    ),
    Task(
        "insert_execute_code_cell",
        "Add a new code cell at the end of the notebook that prints the "
        "dataframe's shape, and run it immediately",
    ),
    Task(
        "insert_execute_code_cell",
        "Insert a quick cell at position 2 that imports numpy, and run it right "
        "away so I can use it in later cells",
    ),
    Task(
        "read_cell",
        "Show me the source code and any output from cell 8 in the currently active notebook",
    ),
    Task(
        "read_cell",
        "What's currently in cell 1 of the open notebook, including its execution count?",
    ),
    Task(
        "delete_cell",
        "Remove cell 9 from the active notebook and show me what was in it before it's gone",
    ),
    Task("delete_cell", "Delete cells 2 and 3 from the currently open notebook"),
    Task(
        "move_cell",
        "Move the cell currently at position 1 down to position 4 in the active "
        "notebook, shifting the others up",
    ),
    Task(
        "move_cell",
        "Relocate the cell at index 5 so it becomes the very first cell in the notebook",
    ),
    Task(
        "execute_code",
        "Quickly run `df.head()` in the active notebook's kernel just to peek at "
        "the data, without adding a cell to the notebook",
    ),
    Task(
        "execute_code",
        "Install the 'seaborn' package into the current kernel with a one-off "
        "command, without saving anything to the notebook",
    ),
    Task(
        "connect_to_jupyter",
        "Point this session at a different Jupyter server running at "
        "http://localhost:8890 using the access token 'xyz789'",
    ),
    Task(
        "connect_to_jupyter",
        "Switch over to a freshly started Jupyter instance on port 8888 that "
        "requires no authentication token",
    ),
]

# ── exp1_blazickjp_arxiv_mcp_server_mirror ───────────────────────────────────────
# 8 tool names read from DOCSTRINGS in exp1_blazickjp_arxiv_mcp_server_mirror.py.
# Generic stub call_tool() — same real-world-intent grounding as the jupyter mirror.
EXP1_ARXIV_MIRROR_TASKS: list[Task] = [
    Task(
        "check_alerts",
        "See if any new papers have shown up for the topics I've been tracking since I last looked",
    ),
    Task(
        "check_alerts",
        "Run through all my saved research topic subscriptions and report anything "
        "new published since the last check",
    ),
    Task(
        "citation_graph",
        "Show me which papers cite arXiv paper 2301.12345, and which papers that "
        "paper itself references",
    ),
    Task(
        "citation_graph",
        "I want the citation network around arXiv ID 1706.03762 — both incoming "
        "citations and its reference list",
    ),
    Task(
        "download_paper",
        "Get the full text content of arXiv paper 2303.08774 saved locally so I can read it later",
    ),
    Task(
        "download_paper",
        "Pull down the complete text of paper 1810.04805 from arXiv for offline reading",
    ),
    Task(
        "get_abstract",
        "Before committing to a full download, show me just the abstract and "
        "metadata for arXiv paper 2005.14165",
    ),
    Task(
        "get_abstract",
        "Give me the title, authors, and summary of arXiv ID 1409.0473 without "
        "pulling the whole paper",
    ),
    Task(
        "list_papers",
        "Which arXiv papers have I already saved locally on this machine?",
    ),
    Task(
        "list_papers",
        "Show me the IDs of every paper I've previously stored for offline access",
    ),
    Task(
        "read_paper",
        "Open the previously saved local copy of paper 2101.00190 and show me its markdown content",
    ),
    Task(
        "read_paper",
        "I already have paper 1912.02292 stored locally — show me its content in readable form",
    ),
    Task(
        "search_papers",
        "Find recent arXiv papers about multi-agent reinforcement learning published this year",
    ),
    Task(
        "search_papers",
        "Look for papers on transformer attention mechanisms written by authors named Vaswani",
    ),
    Task(
        "reindex",
        "My locally stored paper collection's search index seems stale — rebuild it from scratch",
    ),
    Task(
        "reindex",
        "Refresh the local semantic search structure over all the papers I've "
        "downloaded so search results are up to date",
    ),
]

# ── exp1_stickerdaniel_linkedin_mcp_server_mirror ────────────────────────────────
# 17 tool names read from DOCSTRINGS in exp1_stickerdaniel_linkedin_mcp_server_mirror.py.
# Generic stub call_tool() — same real-world-intent grounding as the other mirrors.
EXP1_LINKEDIN_MIRROR_TASKS: list[Task] = [
    Task(
        "close_session",
        "I'm done with LinkedIn for now — shut down the browser session and clean everything up",
    ),
    Task(
        "close_session",
        "Terminate the current automated browsing session and release its resources",
    ),
    Task(
        "get_company_profile",
        "Pull up Docker's LinkedIn company page, including their recent job postings",
    ),
    Task(
        "get_company_profile",
        "Get Anthropic's LinkedIn company overview along with their recent posts",
    ),
    Task(
        "get_company_posts",
        "Show me the most recent posts published on Microsoft's LinkedIn company feed",
    ),
    Task(
        "get_company_posts",
        "What has the company Anthropic posted recently on their LinkedIn feed?",
    ),
    Task("search_companies", "Find LinkedIn companies related to the fintech industry"),
    Task("search_companies", "Search LinkedIn for companies working in electric vehicles"),
    Task(
        "get_company_employees",
        "Show me the people who work at Docker on LinkedIn, along with where "
        "they're based and what they studied",
    ),
    Task(
        "get_company_employees",
        "Get the employee roster and team-function breakdown for the company at "
        "the 'anthropicresearch' LinkedIn page",
    ),
    Task("get_feed", "Show me the latest 15 posts from my own LinkedIn home feed"),
    Task("get_feed", "Pull up what's currently showing on my personal LinkedIn feed"),
    Task(
        "get_job_details",
        "Get the full details for the LinkedIn job posting with ID 4252026496",
    ),
    Task("get_job_details", "Show me everything about job listing 3856789012 on LinkedIn"),
    Task(
        "search_jobs",
        "Find remote software engineer job postings on LinkedIn located anywhere",
    ),
    Task(
        "search_jobs",
        "Look for data scientist openings on LinkedIn based in San Francisco",
    ),
    Task("get_inbox", "Show me my most recent LinkedIn message conversations"),
    Task("get_inbox", "What conversations are sitting in my LinkedIn inbox right now?"),
    Task(
        "get_conversation",
        "Open my LinkedIn message thread with the user 'williamhgates' and show me what was said",
    ),
    Task(
        "get_conversation",
        "Show me the contents of LinkedIn message thread ID 'thr-88213'",
    ),
    Task(
        "search_conversations",
        "Search through my LinkedIn messages for any conversation mentioning 'contract renewal'",
    ),
    Task(
        "search_conversations",
        "Find any LinkedIn conversations in my inbox that mention 'interview scheduling'",
    ),
    Task(
        "send_message",
        "Send a LinkedIn message to 'stickerdaniel' saying 'Great meeting you at "
        "the conference!' and confirm it actually goes out",
    ),
    Task(
        "send_message",
        "Message the LinkedIn user 'williamhgates' with 'Following up on our "
        "conversation' and make sure it's actually delivered, not just drafted",
    ),
    Task(
        "get_person_profile",
        "Pull up the LinkedIn profile for the user 'stickerdaniel', including "
        "their work experience and education history",
    ),
    Task(
        "get_person_profile",
        "Show me williamhgates' LinkedIn profile along with their certifications and skills",
    ),
    Task(
        "search_people",
        "Find LinkedIn users with the title 'software engineer' who are "
        "first-degree connections of mine",
    ),
    Task("search_people", "Search LinkedIn for recruiters at Google"),
    Task(
        "connect_with_person",
        "Send a LinkedIn connection invite to 'stickerdaniel' with a short personal note",
    ),
    Task(
        "connect_with_person",
        "Accept the incoming LinkedIn connection request from 'williamhgates'",
    ),
    Task(
        "get_sidebar_profiles",
        "Show me the 'People you may know' and similar suggested-profile links "
        "from stickerdaniel's LinkedIn page",
    ),
    Task(
        "get_sidebar_profiles",
        "Get the recommended-profiles sidebar links shown on williamhgates' LinkedIn page",
    ),
    Task(
        "get_my_profile",
        "Show me my own LinkedIn profile, including my work experience and skills sections",
    ),
    Task(
        "get_my_profile",
        "Pull up my personal LinkedIn profile page as it currently stands",
    ),
]

# ── Manifest expansion (18 -> 40) ────────────────────────────────────────────
# Tier 1: RW1 (21 tools), RW2 (29 tools), P2A (48 tools) — each catalog's own
# pre-registered TASKS list already has 1:1 tool coverage (verified against each
# catalog's ALL_TOOLS/assert above) and already follows the anti-tautology
# convention (task text expresses intent only). Reused verbatim, once per catalog,
# across every arm of that catalog (arms differ only in served descriptions, never
# in tool names or schemas).
RW1_GITHUB_TASKS: list[Task] = list(_RW1_TASKS)
RW2_AWS_IAM_TASKS: list[Task] = list(_RW2_TASKS)
P2A_INTERNAL_PROXY_TASKS: list[Task] = list(_P2A_TASKS)

# ── Tier 2: Q3 (12 tools) ────────────────────────────────────────────────────
# q3_catalog.TASKS covers 10 of 12 tools (1 task each) — missing lookup_data and
# plan_event, the second tool in each of Q3's two "genuinely equivalent" control
# pairs (find_entries/lookup_data, book_slot/plan_event; see q3_catalog.py's own
# CONTROL_TASK_PAIRS). Gap tasks below give each of those 2 tools its own task,
# phrased distinctly from its equivalent partner's existing catalog task, with a
# concrete literal so it is constrainable (constraints.py).
_Q3_GAP_TASKS: list[Task] = [
    Task(
        "lookup_data",
        "Search for every entry whose key includes the substring 'sess-4471'.",
    ),
    Task(
        "plan_event",
        "Add the 'team-retro' block to the shared calendar for Monday morning.",
    ),
]

Q3_SUBSET_TASKS: list[Task] = list(_Q3_CATALOG_TASKS) + _Q3_GAP_TASKS

# ── Tier 2: Q6 (23 tools) ────────────────────────────────────────────────────
# q6_catalog.TASKS (19 tasks) covers 19 of 23 tools. The 4 gap tools are all
# inherited from Q3's 12-tool catalog but NOT among the 6 tools Q6 kept as its
# "structural contested" subset: save_record, archive_item (store/delete_family),
# lookup_data, plan_event (control pairs — same gap as Q3 above). Gap tasks give
# each its own task with a concrete literal, distinct from any Q3 gap-task wording.
_Q6_GAP_TASKS: list[Task] = [
    Task(
        "save_record",
        "Update the customer profile for account 'CUST-6612', creating it fresh if "
        "this is their first record.",
    ),
    Task(
        "archive_item",
        "Move the outdated marketing record 'promo-2024-q1' out of active results "
        "while keeping it accessible for later reference.",
    ),
    Task(
        "lookup_data",
        "Search for every entry whose key includes the substring 'ticket-8827'.",
    ),
    Task(
        "plan_event",
        "Add the 'quarterly-planning' block to the shared calendar for Thursday afternoon.",
    ),
]

Q6_SUBSET_TASKS: list[Task] = list(_Q6_CATALOG_TASKS) + _Q6_GAP_TASKS

# ── Tier 3: T18 family, 2nd 12-tool subset (data_write + validate) ─────────────
# Mirrors the original 4 T18 entries' approach exactly, but for manifest.py's
# _T18_FAMILY_SUBSET_SET2 (data_write + validate families) instead of
# (data_fetch + notify). t18_catalog.TASKS covers 8 of these 12 tools with 1 task
# each (save_record, write_entry, store_item, persist_row, validate_schema,
# check_permission, verify_token, validate_format); commit_data, insert_document,
# check_quota, verify_signature have ZERO catalog tasks. Gap tasks below add a 2nd
# task to each of the 8 covered tools and 2 new tasks each for the 4 uncovered
# tools, bringing every one of the 12 tools to >=2 tasks — same structure as the
# original _T18_GAP_TASKS (8 covered x1 + 4 uncovered x2 = 16 gap tasks; 8 catalog
# + 16 gap = 24 total, 2 per tool). Unlike the original family pair, most literal
# identifiers here are newly authored (not inherited from catalog task text) so
# every gap task carries a concrete constrainable value.
_T18_FAMILY_SUBSET_SET2: list[str] = _T18_FAMILIES["data_write"] + _T18_FAMILIES["validate"]

_T18_GAP_TASKS_SET2: list[Task] = [
    # data_write — 2nd task for the 4 tools the catalog already covers
    Task(
        "save_record",
        "Update the shipping preferences on file for repeat customer 'CUST-7734', "
        "creating a fresh record if this is their first order.",
    ),
    Task(
        "write_entry",
        "Append today's system health check result for service 'checkout-api' to "
        "the audit trail as a permanent record.",
    ),
    Task(
        "store_item",
        "Keep the dashboard summary for widget 'quarterly-revenue' readily "
        "available for quick access without hitting the database again.",
    ),
    Task(
        "persist_row",
        "Insert a brand-new subscription-renewal row for subscription 'SUB-88213' "
        "into the billing table — this should only succeed if no such row exists yet.",
    ),
    # data_write — new tasks for the 2 tools the catalog never covers
    Task(
        "commit_data",
        "Flush the batch of pending updates queued under batch id 'BATCH-5591' so "
        "they're written to the database all at once.",
    ),
    Task(
        "commit_data",
        "Finalize the queued set of inventory adjustments tagged 'INV-ADJ-220' as "
        "a single atomic write to the database.",
    ),
    Task(
        "insert_document",
        "Add a brand-new customer profile document with id 'doc-cust-4471' to the "
        "NoSQL collection — the operation must fail if that id already exists.",
    ),
    Task(
        "insert_document",
        "Create a fresh order-history document with id 'doc-ord-9012' in the "
        "document store, only if no document with that id already exists.",
    ),
    # validate — 2nd task for the 4 tools the catalog already covers
    Task(
        "validate_schema",
        "Check that the payload submitted by mobile client request 'REQ-3391' "
        "matches the registered data contract before accepting it.",
    ),
    Task(
        "check_permission",
        "Confirm whether support agent account 'agent-2209' is allowed to issue "
        "refunds under the current access policy.",
    ),
    Task(
        "verify_token",
        "Make sure the bearer credential 'tok_9f8e7d' attached to this API "
        "request is still within its valid lifetime and correctly formed.",
    ),
    Task(
        "validate_format",
        "Check that the entered postal code '94107-1234' matches the required "
        "regional formatting pattern.",
    ),
    # validate — new tasks for the 2 tools the catalog never covers
    Task(
        "check_quota",
        "Find out how close account 'ACC-5502' is to hitting its monthly API call limit.",
    ),
    Task(
        "check_quota",
        "Check whether team 'team-data-eng' storage allotment has been used up "
        "before allowing another upload.",
    ),
    Task(
        "verify_signature",
        "Confirm that incoming webhook payload 'wh-8834' cryptographic signature "
        "actually matches what the sender's shared secret would produce.",
    ),
    Task(
        "verify_signature",
        "Make sure update package 'pkg-2.4.1' signature checks out against the "
        "publisher's public key before installing it.",
    ),
]

T18_SUBSET_TASKS_SET2: list[Task] = [
    t for t in _T18_CATALOG_TASKS if t.tool_name in _T18_FAMILY_SUBSET_SET2
] + _T18_GAP_TASKS_SET2

# ── Tier 4: exp1_dataojitori_nocturne_memory_mirror ─────────────────────────────
# 7 tool names read from DOCSTRINGS in exp1_Dataojitori_nocturne_memory_mirror.py.
# call_tool() is a generic stub (json.dumps({"stub": True, ...})) — tasks describe
# plausible real-world intent matching each tool's real public docstring; the stub
# accepts any call regardless of whether it would "really" work. 2 tasks per tool
# (14 total), matching the density of the other exp1 mirrors.
EXP1_NOCTURNE_MEMORY_MIRROR_TASKS: list[Task] = [
    Task(
        "read_memory",
        "Load the memory stored at 'core://agent/my_user' so I can see what it "
        "currently contains before deciding what to change.",
    ),
    Task(
        "read_memory",
        "Show me the recently modified memories from the last session so I can "
        "catch up on what changed.",
    ),
    Task(
        "create_memory",
        "Add a new memory under 'core://agent' with the content 'always confirm "
        "before deleting user data', high retrieval priority, a disclosure "
        "condition of 'when I am about to run a delete operation', and the title "
        "'delete_confirmation_rule'.",
    ),
    Task(
        "create_memory",
        "Record a brand-new note under the 'writer://' root about the protagonist's "
        "backstory, with its own title, priority, and a disclosure trigger for "
        "when a scene involving that character starts.",
    ),
    Task(
        "update_memory",
        "In the memory at 'core://agent/worldview', replace the sentence 'trust is "
        "earned slowly' with 'trust is earned through consistent action' — leave "
        "everything else in that memory unchanged.",
    ),
    Task(
        "update_memory",
        "Append a new paragraph to the end of the existing memory at "
        "'writer://chapter_2' without touching what's already there.",
    ),
    Task(
        "delete_memory",
        "Permanently remove the obsolete memory at 'core://agent/old_note' — I've "
        "already read it and confirmed it's no longer relevant.",
    ),
    Task(
        "delete_memory",
        "Cut the outdated draft path 'writer://draft_v1' from the memory tree for good.",
    ),
    Task(
        "add_alias",
        "Create a second entry point at 'core://timeline/2024/05/20' that points "
        "to the same existing memory as 'core://agent/my_user/first_meeting', with "
        "its own priority and its own disclosure condition for this new path.",
    ),
    Task(
        "add_alias",
        "I want 'core://hazards/network_outage' to also be reachable from a new "
        "path under 'core://agent/infra_notes' without duplicating the content — "
        "set a priority and disclosure condition for the new path.",
    ),
    Task(
        "manage_triggers",
        "Bind the word 'Nginx' as a glossary keyword to the memory node at "
        "'core://hazards/spa_fallback' so a link to it surfaces automatically "
        "whenever that word appears elsewhere.",
    ),
    Task(
        "manage_triggers",
        "Unbind the keyword 'deprecated' from whatever memory node it's currently "
        "attached to, without deleting the memory itself.",
    ),
    Task(
        "search_memory",
        "Find every memory whose path or content mentions the word 'job', across all domains.",
    ),
    Task(
        "search_memory",
        "Look only within the 'writer' domain for any memory mentioning the word 'chapter'.",
    ),
]

# ── Manifest-keyed lookup ─────────────────────────────────────────────────────
# Keys must exactly match ToolSetEntry.name in manifest.py (all 40 entries).
BLIND_TASKS: dict[str, list[Task]] = {
    "echo_server": ECHO_SERVER_TASKS,
    "confusable_server": CONFUSABLE_SERVER_TASKS,
    "confusable_server_oracle": CONFUSABLE_SERVER_TASKS,
    "grounded_server": GROUNDED_SERVER_TASKS,
    "grounded_server_oracle": GROUNDED_SERVER_TASKS,
    "mediocre_server": MEDIOCRE_SERVER_TASKS,
    "call_constraints_server": CALL_CONSTRAINTS_SERVER_TASKS,
    "call_constraints_server_oracle": CALL_CONSTRAINTS_SERVER_TASKS,
    "call_constraints_v2_server": CALL_CONSTRAINTS_V2_SERVER_TASKS,
    "call_constraints_v2_server_oracle": CALL_CONSTRAINTS_V2_SERVER_TASKS,
    "t18_vague_server": T18_SUBSET_TASKS,
    "t18_fixer_server": T18_SUBSET_TASKS,
    "t18_q2b_server": T18_SUBSET_TASKS,
    "t18_oracle_server": T18_SUBSET_TASKS,
    "exp1_datalayer_jupyter_mcp_server_mirror": EXP1_JUPYTER_MIRROR_TASKS,
    "exp1_datalayer_jupyter_mcp_server_mirror_oracle": EXP1_JUPYTER_MIRROR_TASKS,
    "exp1_blazickjp_arxiv_mcp_server_mirror": EXP1_ARXIV_MIRROR_TASKS,
    "exp1_stickerdaniel_linkedin_mcp_server_mirror": EXP1_LINKEDIN_MIRROR_TASKS,
    # ── Tier 1: RW1 / RW2 / P2A (22 new entries start here) ────────────────────
    "rw1_github_mirror": RW1_GITHUB_TASKS,
    "rw1_arm_a": RW1_GITHUB_TASKS,
    "rw1_arm_guardb": RW1_GITHUB_TASKS,
    "rw1_arm_oracle": RW1_GITHUB_TASKS,
    "rw2_aws_iam_mirror": RW2_AWS_IAM_TASKS,
    "rw2_arm_a": RW2_AWS_IAM_TASKS,
    "rw2_arm_guardb": RW2_AWS_IAM_TASKS,
    "p2a_internal_proxy_mirror": P2A_INTERNAL_PROXY_TASKS,
    "p2a_arm_a": P2A_INTERNAL_PROXY_TASKS,
    "p2a_arm_guardb": P2A_INTERNAL_PROXY_TASKS,
    "p2a_arm_oracle": P2A_INTERNAL_PROXY_TASKS,
    # ── Tier 2: Q3 / Q6 ─────────────────────────────────────────────────────────
    "q3_real_server": Q3_SUBSET_TASKS,
    "q3_arm_a": Q3_SUBSET_TASKS,
    "q3_arm_o": Q3_SUBSET_TASKS,
    "q6_real_server": Q6_SUBSET_TASKS,
    "q6_arm_a": Q6_SUBSET_TASKS,
    "q6_arm_f_doc_guarded": Q6_SUBSET_TASKS,
    # ── Tier 3: T18 2nd family subset (data_write + validate) ──────────────────
    "t18_vague_server_set2": T18_SUBSET_TASKS_SET2,
    "t18_fixer_server_set2": T18_SUBSET_TASKS_SET2,
    "t18_q2b_server_set2": T18_SUBSET_TASKS_SET2,
    "t18_oracle_server_set2": T18_SUBSET_TASKS_SET2,
    # ── Tier 4: new real-world mirror ───────────────────────────────────────────
    "exp1_dataojitori_nocturne_memory_mirror": EXP1_NOCTURNE_MEMORY_MIRROR_TASKS,
    # ── Phase 3: LLM-fixer-improved variants (5 new entries) ───────────────────
    # run_fixer only edits description text and per-param schema metadata — never
    # tool names or param names (verified in-process against each pair's
    # list_tools() output before wiring these in). Same underlying tools as the
    # "before" fixture, so the same task list applies verbatim (identical
    # convention to the existing oracle-pair entries above, e.g.
    # confusable_server / confusable_server_oracle sharing CONFUSABLE_SERVER_TASKS).
    "grounded_server_fixed": GROUNDED_SERVER_TASKS,
    "confusable_server_fixed": CONFUSABLE_SERVER_TASKS,
    "mediocre_server_fixed": MEDIOCRE_SERVER_TASKS,
    "call_constraints_server_fixed": CALL_CONSTRAINTS_SERVER_TASKS,
    "call_constraints_v2_server_fixed": CALL_CONSTRAINTS_V2_SERVER_TASKS,
}
