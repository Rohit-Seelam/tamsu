# Build list

- `feature_list.json`: an array of features, each written like this:
  ```json
  {"id": "F001", "category": "feature", "description": "...", "steps": ["a check whose result can be seen"], "passes": false}
  ```
  - `category` is `feature`, `bug` or `owner-action` (work only I can do).
  - A session changes only `passes`, and sets it to true only after running every step and seeing
    the result, in the commit that lands the feature on `main`. With the loop, only the
    orchestrator sets it.
  - I add or amend features. Ones that are no longer needed stay in the list, and I mark them with a
    note.
  - Write it with `json.dumps(features, indent=2, ensure_ascii=False) + "\n"`, so that changing one
    field is a one-line diff.
- `progress.md`: one dated entry per session at the top (State / Judgement calls / Next), plus
  standing Owner decisions and Open risks.
- There is no backlog file. Ideas stay in conversation until I turn them into features.
