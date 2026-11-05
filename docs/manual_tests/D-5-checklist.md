# D-5 manual test checklist: approval with interrupt and resume

About 5 minutes in the browser. Confirms the automated findings in
`spikes/NOTES.md` § D-5 by hand. Needs `OPENROUTER_API_KEY` set.

```bash
uv run streamlit run spikes/hitl_app.py
```

Leave the "Thread ID" field in the sidebar at its default (`demo-thread`)
for steps 1–4.

## Step 1 — propose a write action

Type into the chat box: `Please save the widget with note "looks good"`.

**You should see:** the model's reasoning/tool-call line, then a yellow
"Approval needed: `save_item`(...)" box with three buttons: **Approve**,
**Reject**, **Edit note**. Nothing is saved yet.

## Step 2 — reject it

Click **Reject**.

**You should see:** the buttons disappear; a line showing the model was told
"User rejected the tool call for `save_item`..."; the model's follow-up
reply confirms nothing was saved.

## Step 3 — ask again for the exact same thing

Type the identical message again: `Please save the widget with note "looks
good"`.

**You should see:** if the model proposes the exact same call again, it is
**not** re-asked — no approval box appears, and the reply mentions it is
"not repeating" that already-rejected action. (If the model phrases its
proposal slightly differently - e.g. a different note - you *will* see a
fresh approval box; that is a different action, not a repeat, and is
correctly allowed.)

## Step 4 — restart the app, same thread

Stop Streamlit (Ctrl-C) and run `uv run streamlit run spikes/hitl_app.py`
again. Leave the Thread ID as `demo-thread` and open the page.

**You should see:** the full chat history from steps 1–3 is still there,
loaded from `spikes/fixtures/d5.sqlite` - nothing was lost by restarting the
process.

## Step 5 — approve and edit

Change the Thread ID in the sidebar to something new, e.g. `demo-thread-2`,
then type: `Please save the gadget with note "check later"`.

- Click **Edit note** this time. **You should see:** the saved note includes
  "(edited by reviewer)" appended - the reviewer's edit took effect, not the
  model's original text.
- Ask again for a different item, e.g. `Please save the gizmo with note
  "maybe"`, and this time click **Approve**. **You should see:** the model
  confirms the save; no approval box remains.

---

Cleanup: delete `spikes/fixtures/d5.sqlite` afterwards if you want a clean
slate (it is gitignored, so this never affects version control).
