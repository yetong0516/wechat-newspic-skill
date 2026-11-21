# WeChat draft delivery

The API client handles only authentication, permanent image upload/readback, `draft/add`, `draft/update`, `draft/get`, complete `draft/batchget` and read-only `freepublish/batchget`. It never publishes, mass-sends or deletes. It does not change system networking.

## Credentials and local records

Use `WECHAT_APP_ID` and `WECHAT_APP_SECRET`, or put a JSON file with `app_id` and `app_secret` outside the repository and pass `--credentials /private/path/credentials.json`. Do not paste secrets into prompts, examples, command arguments or source files. The account needs the corresponding API permissions and the request IP in its WeChat allowlist.

Requests use the process's proxy environment by default. `--direct` ignores it for this client process only; use it only when appropriate for the user's network. Never run a script that disables the proxy or VPN.

`.wechat/` stores private account fingerprints, upload caches, snapshots, request audit, submitted payload, save state and readback evidence. It is ignored by Git. The audit contains endpoint names and HTTP status, not authenticated URLs or credentials. Authentication errors expose only a safe error code and, for 40164, the allowlist IP.

## New draft

Complete local review and obtain or verify the existing task/account authorization, then:

```bash
python scripts/wechat_draft.py plan drafts/my-post
python scripts/wechat_draft.py inspect drafts/my-post
python scripts/wechat_draft.py save drafts/my-post --confirm-draft-save
```

`plan` makes no network calls. `inspect` reads every draft page. `save` repeats duplicate and publication checks, uploads images with a per-account hash cache, rechecks before writing, creates once and verifies. If another draft matches the title, source or configured aliases, creation stops. A known saved ID is verified rather than created again. Distinct articles on the same paper require deliberate identity reconciliation; the tool does not merge them.

## Update an existing draft

```bash
python scripts/wechat_draft.py inspect drafts/my-post
# Read .wechat/snapshot.json, reconcile the backend's edits into local content,
# re-render and review, then:
python scripts/wechat_draft.py save drafts/my-post --confirm-draft-save \
  --update EXISTING_MEDIA_ID --snapshot drafts/my-post/.wechat/snapshot.json
```

The snapshot must belong to the account and target. Its stable fields are checked immediately and again after uploads. Changes cause a stop before `draft/update`. Existing comment settings and crop coordinates are preserved. Only a single-article `newspic` draft is supported. The tool cannot infer which user edits to keep; reconcile them before the update.

## Readback and recovery

```bash
python scripts/wechat_draft.py verify drafts/my-post
```

Verification compares complete UTF-8 text, type, requested crops, first-image cover, ordered material IDs, all remote image bytes and dimensions, author when returned, uniqueness and publication records. Extra server-supplied crop ratios are accepted only if requested coordinates are preserved. Missing `author` is stored as null; it is not evidence of an author match. `published=false` is verified only after the read-only publication traversal succeeds.

- **40164:** show the newly reported IP; ask the account owner to allowlist it and save. No images or draft writes occur if authentication fails. Existing authorization survives the retry.
- **Explicit API rejection:** state becomes `save_rejected`; fix the reported cause, then retry with full prechecks.
- **Network failure during a write:** state remains `outcome_uncertain`. Do not blindly repeat `save`. Run `inspect`; an exact title/caption/material match can recover the existing ID. Then run `verify`. An unresolved outcome remains blocked from automatic creation.
- **Readback failure after a successful write:** the ID remains stored as `saved_unverified`. Retry `verify`, not a second creation.
- **Different bytes or text:** keep the evidence and inspect the backend before deciding whether a correction is needed. Never overwrite subsequent edits simply to satisfy the checker.
- **Stale local lock:** confirm no save is running, inspect remote state, then remove the specific stale `.wechat/write.lock` manually.

A local lock and a final duplicate check reduce duplicate risks, but WeChat provides no transaction spanning multiple machines. Avoid simultaneous saves of the same post from different clients. Publishing remains a separate human operation outside this tool.

Official endpoint reference: [WeChat draft/add](https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_add). The standalone extraction is validated with offline API simulations; its source workflow has been used for a seven-page draft and full readback. No real-account calls are made by repository tests.
