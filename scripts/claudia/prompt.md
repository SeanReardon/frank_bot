# Claudia Agent Instructions

**NOTE**: This file is for documentation only. The actual prompt template
used by the worker is at `claudia/scripts/claudia/prompt_template.py`.

This file exists in managed repos for reference, but the worker dynamically
generates prompts from the central template. To change agent behavior,
edit `prompt_template.py` in the main claudia repository.

## Overview

Claudia works in **batch mode**, processing up to 5 tasks per iteration:

1. Read PRD at `scripts/claudia/prd.json`
2. Pick top N incomplete tasks (by priority)
3. Implement ALL tasks in a single session
4. Update `passes: true` for completed tasks
5. Append to `scripts/claudia/progress.txt`
6. Commit and push
7. Verify GitHub Action passes

## Stop Conditions

- `<promise>COMPLETE</promise>` - All tasks succeeded
- `<promise>PARTIAL: X of N completed</promise>` - Some tasks blocked
- `<promise>BLOCKED: reason</promise>` - No tasks could be completed

## See Also

- `claudia/scripts/claudia/prompt_template.py` - Authoritative prompt template
- `claudia/prompts/bootstrap.md` - Bootstrap prompt for new repos
