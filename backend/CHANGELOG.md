# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.9.5] — Unreleased

### Added
- `rotate_encryption_keys.py --verify` checks that every encrypted value and vault file opens under the current keys, without changing anything. The key-rotation guides now end with it.

### Changed
- Deleting a large engagement is much faster: the database removes its findings, assets, test cases and their children in one step instead of one row at a time.

### Fixed
- Edits made in a shared note or field while your connection was down now reach the other editors when you reconnect; before, they could stay on your screen only. Joining a busy shared document also no longer sends the whole document to every other editor.
- Every open tab no longer receives the full list of signed-in users, with photos, each time someone opens or closes a page. That list was never displayed, and the traffic grew with the square of the number of users online.
- Database downgrades (`migrate.py downgrade`) work again for every revision, down to an empty database; several failed partway. Unused leftover enum types are removed on upgrade.
- Users who can view all engagements now see an engagement's findings, assets and test cases (and find them in search). Those tabs used to come back empty for them unless they were also a member.
- A review comment anchored on a phrase that appears more than once with the same surrounding text now stays on the copy it was left on, instead of moving to the first one.
- Scan imports: Burp findings keep their reference links (they were dropped) and show lists on separate lines; Nessus hosts scanned by name keep that name instead of the IP.

## [1.9.4] — 2026-11-27

### Changed
- The frontend runs on Node.js 24 LTS (was 22); rebuild the frontend image when upgrading.
- **Backups no longer include `.env` (the encryption keys).** Keep `VAULT_ENCRYPTION_KEY` / `TOTP_ENCRYPTION_KEY` in your secret store, as the guides advise; `BACKUP_INCLUDE_ENV=1` restores the old behaviour. Backups now record key fingerprints, and restoring a backup with different keys is refused. A weekly restore drill (`backup.sh --verify`, Sundays 04:30) checks the newest backup restores and decrypts, failed runs no longer count toward retention, MinIO is archived stopped for a consistent copy, and `BACKUP_*` settings can live in `.env`.
- The Notes editor now uses the same editor as findings, test cases and assets: the full toolbar with tooltips (lesser-used controls under More), @mentions, pasting a URL over selected text to make a link, and a Saving/Saved indicator. Undo in a shared note now only undoes your own changes.

### Fixed
- **Frontend security updates.** Next.js 15.5.29 (fixes, among others, remote-code-execution and denial-of-service advisories in the image optimizer and Server Actions), axios 1.21.1, TipTap 3.35 / ProseMirror (paste XSS), DOMPurify, zod and PostCSS, plus transitive packages; `npm audit` goes from 31 advisories (1 critical, 14 high) to 2 low.
- **Diagram rendering updated to mermaid 12**, closing its prototype-pollution and CSS-injection advisories; diagrams look slightly different (wider nodes, soft shadow).
- Backend security updates: python-multipart 0.0.34 (form-parsing denial-of-service advisories) and Markdown 3.11.3. Backend and MCP server dependencies are now fully locked, so every build installs the same versions.
- AI chat no longer keeps a database connection open while a reply streams or waits for a tool approval, which could exhaust connections with several chats open and stall database migrations during an upgrade.
- Paging through notifications, activity logs, scan imports and the Security Center no longer repeats some entries and skips others when several share the same time (or, in the activity log sorted by action, the same action).
- Deleting an asset, or an engagement with its assets, now also removes the Shodan and ServiceNow CMDB enrichment data stored for those assets; data left behind by earlier deletes is cleaned up on upgrade.
- The dashboard loads faster: its statistics now take 9 database queries instead of 33 and no longer load every finding and test case of your engagements to count them.
- The ATT&CK matrix now uses the standard severity colours (Medium yellow, Low light blue, Info grey) to match the rest of the app.

## [1.9.3] — 2026-11-24

### Fixed
- **Security Center account actions respect the user-management ceiling.** A delegated security manager could disable or sign out team leads, read-only admins and accounts holding permissions they don't; only admin accounts were protected. It now follows the same rule as admin user management.
- **The engagement activity log hides what you can't open.** Members without a resource's view permission (for example the vault) no longer see its entries' names and change details in the activity log; the activity feed already worked this way. Users with view-all access now see the non-vault entries too.
- **Sign out everywhere also ends sessions started the same second.** Tokens issued earlier in the second a password change, 2FA change or forced sign-out happened could keep working until they expired. Revoked tokens also stay revoked on servers not set to UTC.
- **Automations lists every organisation rule you can open.** Without an admin or team-lead role you only saw the rules you wrote, although you could open and edit the others.
- **Saving with a reference that no longer exists explains what's wrong.** Picking a client type, marking profile or similar that had been deleted meanwhile gave a server error; it now names the field. Listing the same ATT&CK technique twice on a finding or test case no longer fails the save.
- **Renaming a permission group no longer shows an error.** The rename was saved, but the page reported a failure. Group responses also show the actual member count instead of 0.
- **Deleting a user no longer deletes their automation rules and reviews.** Organisation rules they wrote and peer reviews they left are kept, without an author. Their personal rules are still removed.
- **Linking reports failures.** If some links in the link dialog couldn't be saved, it showed a success message and closed. It now shows an error with the reason and stays open.
- **Sessions stay signed in with short token lifetimes.** If `ACCESS_TOKEN_EXPIRE_MINUTES` was set below 28 minutes, the background refresh came too late and requests briefly failed and were retried. It now refreshes shortly before the actual expiry.
- The sign-in and registration pages show the installed version instead of a fixed "v2.0".
- **Copy buttons tell you when copying fails.** Copying a temporary password, API token, recovery codes or similar showed "copied" even if the browser blocked it. It now shows an error instead.
- **Muting an event in the app actually quiets it.** With an event's *Site* notifications turned off, new ones still raised the unread badge; they're now stored as read and only appear in the history.
- **Engagements without a start date no longer show 12/31/1969** or crowd the top of the engagements list; they show a dash and sort last.
- **Email and 2FA changes always end API tokens.** If session revocation failed partway, an email change or 2FA enable/disable could leave the account's API tokens working. They're now ended together with the change.
- **One asset per host in an engagement.** Adding an asset whose identifier (IP, hostname, URL) already exists in the engagement, in any letter case, now says so instead of creating a duplicate, and password-spray imports match existing assets regardless of case. Existing duplicates are merged into the oldest one when you upgrade.
- Leaving a new finding, asset or test case, the runbook builder, or the report layout / theme editors with unsaved changes now asks first, like the edit pages.
- Engagement status menus (list filter, new engagement, status control) list Scoping before Planning, matching the lifecycle.
- Engagement members without the note_view permission no longer see linked notes' titles in the findings / test case / asset / vault / cleanup tables.
- Engagement statuses use one colour palette everywhere (the planning page's): the engagements list, status control, dashboard widgets, stats charts and remediation previously used a different mix.
- Engagement phases now follow changes to the engagement's dates (including dates added after creation), unless a phase's dates were adjusted by hand.
- Attack-chain links that would make a loop through three or more items are refused, not just direct back-links.
- Scan imports (Nessus, Burp, Nuclei) keep each host's evidence — port or location and the scanner's output — in the merged finding's technical details, instead of only the first host's.
- Deleting someone else's draft template or runbook follows the manage / runbook_delete permission instead of the admin role, and the templates page offers Delete on the same terms.
- Hash lookup recognises LM:NT pairs and pwdump / secretsdump lines (user:rid:LM:NT:::) and looks up the NT hash, instead of reporting an unrecognised format.
- Saving a finding, test case, asset or engagement with a blank required field (title, name, identifier, start date) stops with a message instead of saving a whitespace title or failing with a validation error.
- Scoring a finding with malformed calculator inputs (a non-text CVSS value, NaN / infinite / out-of-range DREAD or OWASP numbers) is rejected with a clear error instead of failing or storing an invalid score.

## [1.9.2] — 2026-11-22

### Changed
- **Responses load only the links they show.** The 35 `lazy="selectin"` relationships on findings, assets, test cases, vault items, cleanup artifacts, notes, intel/infra items, spray campaigns and runbook items chained into each other: one finding loaded its assets, every asset's ports, findings, test cases, vault items (decrypting them) and cleanup items, and so on. They are now `lazy="raise"` (an unloaded relationship is an error, not a hidden query), and each response loads one level from a shared set in `models/loaders.py` (`options("FINDING")`, `load(db, Model, id)` after a create or update). On dev data one finding went from 11 statements / 94 objects to 7 / 8, and an engagement's findings from 35 / 171 to 7 / 71. Spray campaigns no longer load every result row unless the endpoint asks for them.
- `User.recovery_codes_remaining` is a count subquery on the user row instead of loading every recovery code on each authenticated request.

- **One AI tool registry.** The MCP server's 50 tools and the in-app chat's tools were separate hand-kept lists (plus a third static list behind `/ai/mcp/tools`). They now come from `backend/utils/ai_tool_registry.py`: each entry carries the tool's schema and the API route it calls. The MCP server reads it from `GET /ai/tool-registry` and dispatches generically (its enum mirrors and per-tool branches are gone; the write gate, UUID/pattern checks, vault redaction and untrusted-data wrapper stay in the MCP server). `tests/test_ai_tool_registry.py` checks every entry against the real routes and request schemas.
- **One report document behind every format.** `utils/report_content.py` builds what a report says (finding and test-case order, `F01`/`T1` ids, fields and labels, statuses, custom fields, evidence, and each portion's effective mark plus the banner); the PDF, Markdown and interactive HTML renderers keep their own layout and render from it.
- **Markdown reports are marked.** With a marking profile they open and close with the banner, carry portion marks on section, finding, test-case and cleanup headings (and a mark column in their tables), and end with the distribution statement. Findings are headed by their report id (`F01: ...`) as in the PDF and HTML reports, and test cases get detail entries, not only a table row.
- The interactive HTML report shows report-visible custom fields and the portion marks of test cases, cleanup items and evidence.
- **Deploys wait for health and can roll back.** The backend, frontend and MCP server have healthchecks; `deploy_server.sh` starts the stack with `docker compose up -d --wait` instead of a fixed `sleep 15`, and stops with the failing service's logs if one doesn't come up. Each deploy that starts from a healthy install keeps a rollback point (the running images tagged `:previous`, plus its pre-deploy database snapshot), and `./deploy_server.sh --rollback` restores both after saving a dump of the current database.
- `backup.sh --restore-db <dump>` replaces the database safely: it stops the app containers, recreates the database empty and restores into it.
- CI typechecks and lints the frontend and builds the backend, frontend and MCP server images (`.github/workflows/frontend.yml`, `images.yml`).

### Fixed
- Cleanup items in generated reports now get their linked finding (the report loaded only their assets).
- AI tool schemas that didn't match the API, found by the new registry test: `create_testcase` / `create_testcase_template` didn't require `category` and `description` (calls without them 422'd); `create_asset` / `update_asset` offered `os`, the vault tools `url` and `notes` (the field is `note`), the finding-template tools `severity`, and `update_testcase` `status` / `result` (it's `actual_result`, `is_executed`, `is_successful`) — none of which the API takes, so they were dropped silently.
- The in-app chat's `list_notes` tool was advertised but had no executor ("Unknown tool"); its system prompt also promised vault, cleanup and template tools it doesn't have.
- A zip deploy extracted a new `deploy_server.sh` over the copy that was running, and bash went on reading the new file mid-run. The script is now one function, read whole before it starts.
- The restore command printed after the pre-deploy snapshot (`pg_restore --clean` over the live database) left the newer release's tables behind, and the backend crash-looped re-running the migrations that created them. The documented rollback (check out the old tag and rebuild) crash-looped as well, because the old backend didn't know the database's revision.
- Changes to nginx's config weren't applied by a redeploy (`up -d` leaves an unchanged container running); nginx is now recreated on each deploy.
- Certbot had no restart policy, so a crash or reboot stopped certificate renewal.
- PDF and Markdown reports left out a finding's Technical Details (only the HTML report showed them).
- A sub-test's display id in the PDF attack graph and the HTML report came from list order, so a child could be numbered before its parent; ids now follow the test-case tree the PDF lists.
- A scan or asset import that named the same host twice (Burp vhosts on one IP, a host repeated in an nmap run) or listed a port twice failed with a server error and imported nothing. Repeated hosts now merge and repeated ports are added once.
- Opening a note recorded you as its last editor (and bumped its modified time) even if you changed nothing, and every keystroke, yours or a co-editor's, made each open editor send the whole note to the server. Notes are now saved after a pause in your own typing (and when you leave the page), and a save that changes nothing is ignored.
- Changing only a finding's custom fields on its edit page didn't count as an edit: Save stayed disabled and leaving the page didn't warn about unsaved changes.
- The AI settings form showed defaults for the context budget, recent turns kept and compaction threshold (the settings endpoint didn't return them), so saving the form reset them. A stored "keep recent turns" of 0 also compacted away the turn being answered; it's at least 1.
- PDF reports in a theme set to Times Roman failed to generate (bold text asked ReportLab for "Times-Roman-Bold", which doesn't exist). Theme fonts are now limited to the three the editor offers.
- JSON + attachments exports were named after the last evidence file instead of the engagement, and two evidence files with the same name overwrote each other in the archive. Each file is now prefixed with the start of its evidence id (the JSON's `attachment_path` matches).
- A password reset turned 2FA off but left the account's recovery codes, and turning 2FA back on added new codes without removing the old ones, so codes from before the reset worked again. Both now remove the earlier codes.
- The authentication settings page showed the first and last four characters of the LDAP bind password; it's now fully masked.
- The only active admin could change their own role or deactivate their account, leaving the install with no admin. That's now refused until another user is an admin.
- Changing a user's email to one another account already has returned a server error instead of saying so (409). An admin's change to a user's email is now recorded in the security events log, as role and active-status changes are.
- A note could be overwritten with an empty one: when the server asked for the note's text to save, it could ask a browser that had just opened the note and hadn't loaded it yet, and a slow load let you type into the empty editor. The server now asks whoever made the last edit, and the editor accepts typing and saves only once the note has loaded.
- Renaming a client left the old name on its engagements (in search, reports, the calendar and stats). Renames now carry over, and upgrading fixes engagements of clients renamed before.
- Comparing engagements showed zero findings for an engagement with no client, and refused engagements a user could open through the "view all engagements" permission.
- A 2FA secret that could no longer be decrypted (after an encryption key change) made login and the 2FA settings fail with a server error; the code is now just rejected as invalid.
- An API token expiry given with a UTC offset (`+05:00`) had the offset dropped, so the token expired that many hours late (or early).
- Setting `REFRESH_TOKEN_EXPIRE_HOURS` above 24 still ended sessions after a day: the refresh cookie's own lifetime was fixed at 24 hours.
- NetExec scan imports didn't record the command line that produced them.
- Updating an engagement with `tag_ids: null` (documented as "leave the tags alone") removed all its tags.
- A vault file could be changed to another item type, after which it couldn't be downloaded, and other items could be changed into files with no file attached.
- Re-importing a scan didn't link an existing finding to hosts it was newly found on, didn't update a known port's state, service or version, and didn't mark existing hosts as scanned.
- Filtering assets by port, service or version multiplied each asset's open-discussion count by its number of matching ports.
- Sorting the assets table by "Created by" or by discussions sorted by creation date instead.
- Spray imports from NetExec logs turned informational lines such as `Domain: lab.local` into credential attempts (and "successful" ones into vault entries), cut passwords at the first space, recorded an empty password as unknown, and skipped lines whose target was a hostname or IPv6 address.
- Phase health on the planning page and the engagement edit page treated Planning as coming before Scoping, so an engagement still in Scoping showed its Planning phase as complete. The edit page's status list is in lifecycle order and includes Proposed.
- Generate on the Reports page built the report and then did nothing with it; it now downloads.
- The New Finding page had a Status picker that did nothing (findings always start Open); it's removed.
- The AI assistant panel could drop words from a streamed answer where a network read ended mid-line.
- Ticking "always allow" for a tool in the AI chat didn't apply to further calls in the same answer.
- Calendar auto-assign suggestions listed the names and clients of every engagement a suggested user was on, including ones the caller isn't on; they're now limited the same way as team availability. Completed engagements no longer count towards a user's load.
- **Security:** an engagement member allowed to edit only their own findings could add and remove test case, vault item and cleanup links on other people's findings. These links now need permission to edit any finding.
- **Security:** the AI provider API key was stored unencrypted in the database (the "encrypted" flag only hid it in API responses). AI settings are now encrypted at rest like the other secrets; existing values are encrypted on first startup after upgrading, and key rotation covers them.
- Installs from a git clone never got the daily backup job (the deploy script looked for `backup.sh` only in the install root), and installing it by hand with `scripts/backup.sh --install-cron` wrote a path that doesn't exist into the cron job.
- The deploy script aborted when `.env` had an inline comment, a value with spaces or a `$` in a value; it now reads `.env` the way Docker Compose does.
- If a deploy that generated new encryption keys failed before re-keying existing data, running it again skipped the re-key and left vault and 2FA data unreadable. The pending re-key is now remembered until it succeeds.
- The temporary self-signed certificate expired after one day (on-prem installs keep it), and its presence made the first Let's Encrypt request fail. It now lasts 825 days, is renewed by the deploy script when close to expiry, and is moved aside for the Let's Encrypt request.
- Requests that got a 401 while the background token refresh was running (or while a failed refresh was in flight) never finished, leaving the page stuck loading.
- Live updates and shared notes reconnected every two seconds forever when the server refused the connection, and stopped trying after a few minutes during a real outage. They now stop on a refusal, keep retrying through outages, and reconnect as soon as the network or tab comes back.
- Deleting a finding, test case, asset, note or engagement left its edit history in the database. It is now deleted with it, and an upgrade migration removes the history already left behind.
- On new installs the built-in finding and test case templates were drafts visible only to the first admin. They are now published, and the upgrade publishes the ones already seeded as drafts.
- Global search: lowercase "and", "or" and "not" were treated as operators; `engagement:` and `client:` filters, bare scopes like `vault:` (and the page's quick filters built on them) did nothing; `NOT` hid every result with an empty field; and relevance only reordered the most recent results. All work as documented now.
- Deleting a test case template silently removed it from every runbook that used it. Templates in use can't be deleted now; the error names the runbooks.
- Dashboard: the "Last 7d vs Prior 7d" widget compared against a fixed week from when the server was first started; time-series widgets showed the oldest dates instead of the newest when there were more than fit; and labels read "Severity.CRITICAL" instead of "CRITICAL".
- Live notifications were pushed before they were saved, so the notification list and unread badge could refresh without the new one, and a notification whose action then failed was still pushed and emailed. The push and email now wait until it is saved.
- LDAP users whose directory entry has no email address were created with the email "[]", and after the first one, further such users couldn't sign in. They now get a `<username>@ldap.local` address.
- Plugin tabs on the engagement page that require an engagement permission (such as the ServiceNow CMDB tab) were only shown to admins. Members with that permission on the engagement now see them.
- Enabling a plugin that was disabled when the backend started showed it as active, but its pages returned "not found" until a restart. The admin page now says a restart is required, and the plugin's menu items and tabs stay hidden until then.
- **Security:** a role manager whose only access was "view all engagements" could add vault access to engagement roles, though view-all itself never grants the vault; and couldn't add note or cleanup viewing, which it does grant. The limit now matches what view-all grants.
- HTML reports showed code with `&lt;` in place of `<` and dropped blockquotes, and markdown exports deleted any text written in angle brackets (`<username>`, `List<String>`, code like `cat <file>`). Both now keep the text as written, and raw HTML in a finding still can't run in either.
- PDF reports italicised text between underscores inside identifiers and paths (`xp_cmdshell via sp_configure`, `2 * 3 * 4`, `~/.ssh … ~/.bashrc`) and showed the editor's escaped underscores as backslashes. Emphasis now only applies where markdown would put it.
- A test case or cleanup item with a field longer than a page (long steps, a big code block) made PDF generation fail outright, and those fields were cut at 3,000 characters. They now continue onto the next page, untruncated.
- A report item marked with a classification level the report's marking profile doesn't define (e.g. marked under IC/DoD, report run under TLP) was left out of the banner roll-up, so the banner could understate the document or be missing, and BLOCK enforcement didn't catch it. Such levels now always raise the banner, and BLOCK/WARN flag them.
- JSON/ZIP exports of a marked engagement had no classification on any item and no banner. Each exported item now has its effective classification and portion mark, and the export carries the document banner and distribution statement.
- Interactive HTML reports shipped sample content from the template design: a fake "Meridian Financial" scope and methodology page, made-up remediation numbers and a sample timeline on the overview, and wrong sidebar counts. Every page now shows only the engagement's own data. Scope & Method shows the engagement's scope, objectives and the layout's text sections (which this format previously left out). Non-image evidence is listed instead of dropped, captions no longer show `&amp;`, and `·`/`–` display correctly when the file is opened from disk.
- The "chain, in words" list in interactive HTML reports showed blank step numbers, bare IDs and no notes. Each step now reads "source → target" with names, the operator's note, and a link to the finding.
- Generating a report while the layout builder had unsaved changes produced a report without them. Generate now offers to save the changes first.
- Editing a note's title and switching to another note (or leaving the page) within a second or two lost the edit, and another user's update could overwrite a title you were typing. Both are fixed.
- API tokens (admin and profile), authentication settings, engagement export and AI chat failed once your session's access token expired instead of refreshing it, and revoking an API token could report success when the server refused. They now refresh like the rest of the app and show real errors.
- Automation rules on "Evidence Uploaded" only fired for test case uploads, not for evidence added to findings or engagements. They now fire for all three.
- **Security:** a user who was deactivated, or removed from an engagement, kept receiving that engagement's live updates (and their notification feed) until they closed the tab. Open connections now re-check access every 15 seconds and are closed once it's gone.
- In timezones away from UTC, calendar views missed events near the edges of the range shown, such as an early-morning event in US Pacific time missing from its own day. Views now query in the same local time the events are entered in.
- A collaborator joining a note that others were already editing could, after a brief Redis hiccup or on a room left open for over a day, load a second copy of the note's text into it. Each server worker now re-publishes its open connections every 10 seconds.
- One collaborator with a stalled connection (e.g. a sleeping laptop) could delay live updates for everyone on the same engagement, and slow down the save that triggered them. Updates now go out to everyone at once, and a connection that doesn't accept one within 5 seconds is dropped so it reconnects.
- Long AI-assistant chats re-summarized the whole earlier conversation on every new message once they reached the context limit, so each message cost more as the chat went on. Compaction now builds on the previous summary, and a failed summary is retried instead of being reused for an hour.
- Exporting an engagement silently left out any evidence or vault file that couldn't be read from storage, and importing silently dropped rows whose file was missing from the archive. Both now warn, and the export manifest lists the missing files.
- "Strip EXIF" on evidence lowered JPEG quality, made phone photos display sideways, reduced animated images to their first frame, and removed the capture date it was documented to keep. It now removes only identifying metadata (GPS, camera, etc.) and leaves the image itself as it was.
- AI ATT&CK auto-suggest on a large engagement could run past the server's timeout and lose every suggestion it had made. It now works through items one request at a time and shows its progress.
- The ATT&CK Navigator export left out techniques mapped only on test cases. They're now included, shown in green as "Tested, no finding".
- Some Burp Suite XML exports were sent to the Nmap parser on import and imported nothing. The format is now detected from the file's real root element, and an XML file of an unsupported format gets a clear error.
- Opening and saving a dashboard widget grouped by two columns (such as the Severity × Status heatmap) in the widget editor dropped the second column and broke the widget. The editor now keeps it.
- On an attack graph with a pinned layout, every node added after pinning was drawn in the same top-left spot, on top of each other. New nodes are now placed beside the nodes they connect to.
- "Remediate all assets" on a finding could un-remediate an asset a colleague had just marked remediated, and so could ticking a checkbox on a page that wasn't up to date. Both now set the state you chose instead of flipping it.
- Deleting a test case left its evidence behind as unattached engagement evidence. It's now deleted with the test case, as a finding's evidence is; evidence that's also on a finding stays with the finding.
- Built-in defaults an admin deleted (tags, types, templates, groups, engagement roles) came back after every server restart. Each default is now created only once, and a problem in one kind of default no longer stops the others from being set up.
- With an LDAP CA certificate configured, every LDAP login left a certificate file behind in the server's temp directory. The certificate is now passed in memory.
- Logging out with an API token, or with a malformed token, returned a server error. It now succeeds (an API token isn't revoked by logout).
- Threat-intel feed entries without a link were added again on every refresh, and feeds published as a plain JSON list never loaded. Both are fixed, and the intel list loads faster.
- The Shodan plugin's "Rate limit (per minute)" setting had no effect. It's now enforced, and manual lookups reuse recently fetched results instead of spending API quota again.
- SAML sign-in and SP metadata failed with a server error when the SP entity ID was left blank. A blank ID now defaults to the metadata URL, and a broken SAML setup returns a clear "not configured" message.
- Changing a calculator-scored finding's severity or CVSS by hand kept the old calculator inputs, which no longer matched the score. The finding now counts as manually scored.
- Clearing an engagement's name through the API saved it as blank and returned a server error, and clearing its client returned a server error. A blank name is now rejected, and a cleared client unlinks the client.
- Editing, replacing or deleting evidence that wasn't tied to an engagement returned a server error even though the change was saved, and the change was missing from the activity log. It now succeeds and is logged.
- A cleanup artifact created as Cleaned didn't record who cleaned it or when, and one moved back out of Cleaned still showed it as cleaned. Both now follow the status.
- Unpublishing a template or runbook created by someone else hid it from every manager. It now goes back to the review queue instead.
- Attack graph: an attacker's link to an item that was later deleted kept showing as a link to nothing. Such links are now removed.
- Deleting a password wordlist while it was still importing left part of the list behind. The import now stops and removes what it added.
- Scan imports: Nuclei no longer stores the CVSS score as the vector, keeps every port seen for a host, and handles IPv6 hosts; Nmap ports reported as closed|filtered no longer import as open; an httpx line with an invalid port no longer fails the import; and asset CSVs saved by Excel (Windows-1252) import instead of failing.
- The attack-chain panel showed executed test cases that had no result yet as "Fail". They now show as "Executed".
- Attack graph: saved layouts pinned by a since-deleted user disappeared from the layout list. They're listed again.
- Previewing the same password-spray log more than once saved a new copy to the vault each time. It's now saved once, and oversized spray logs are refused.
- Users without calendar edit permission could add their own out-of-office entry but not change it. They can now edit their own.
- An automation rule that still listed a deleted user could stop its notifications from reaching anyone. Deleted and deactivated users are now skipped.
- Clearing a discussion thread's title through the API returned a server error. It's now rejected with a clear message.
- Discussions: an edited comment now updates for everyone viewing the thread, and plugins subscribed to thread and comment events now receive them.
- Restoring an earlier version was blocked when someone was only viewing the record, yet allowed while the same user had it open for editing in another tab (which would then save the old text back). Viewers no longer block it, and the other tab does.
- Live co-editing: when a collaborator's connection dropped abruptly, their cursor could stay on screen and the next auto-save could be lost. A dropped connection is now cleaned up like a normal disconnect.
- Email: leaving the SMTP port blank broke sending and the SMTP settings page, and port 465 with TLS turned off hung until it timed out. A blank port now means 587, and port 465 always uses TLS.
- Statistics: operators with no findings in the chosen date range disappeared from the operator table, evidence not attached to a finding wasn't counted, average CVSS included non-CVSS risk ratings, and calendar team utilisation counted read-only accounts. All fixed.
- MCP server: the AI chat tool failed on some model responses and returned an empty answer when the AI provider reported an error; it now returns the answer or the error. Sessions whose token was revoked now say so.
- Text longer than a field allows now gets a clear "too long" error instead of a server error, and an evidence upload with an over-long description no longer leaves the uploaded file behind.
- Security: passwords set through a password reset, by an administrator creating a user, or at a forced password change are now held to the same 72-byte limit as other passwords (beyond it, the extra characters didn't count).
- Database migrations failed when the database password contained a "%" character. They now run.
- Report layout templates silently discarded classification and page-break settings sent for their sections. They're now refused, since templates don't store them.
- Deleting an engagement left behind the stored files of older evidence that was linked only to one of its findings or test cases. Those files are now removed too.
- Docs: development migration commands now target the development setup, and the plugin install steps now work on a production install.
- SAML sign-in could fail with "request too large" for identity providers that send many attributes or groups. The sign-in callback now accepts larger responses.
- Docs: the MCP server isn't reachable from outside on a default production install. The Admin Guide now says so and explains how to opt in.
- Test pipeline: a storage service that fails to start now fails the run immediately, with its logs.
- A brief backend outage (for example during an update) logged everyone out. The app now waits and reconnects, and signs you out only if the session is actually rejected.
- Several screens (counts, stats, the attack graph, linked items, user pickers) showed stale data after an edit until the page was reloaded. They now refresh.
- In shared editing, collaborators who weren't typing kept disappearing from and reappearing in the presence list. They now stay listed while connected.
- The weak-password warning for infrastructure credentials checked every keystroke and kept each partial password in browser memory. It now checks once you stop typing and keeps nothing.
- Signing in as a different user in one browser tab left other open tabs showing the first user while acting as the second. Those tabs now reload as the new user.
- If the engagement selected in the header was deleted or you lost access to it, it stayed selected and the dashboard kept trying to load it. It's now cleared.
- Logging out on a slow connection could leave the session valid on the server. Logout now waits (up to 3 seconds) for the server to end the session.
- Opening an engagement no longer sends a request whose result was never used.
- The evidence page showed edit and delete buttons to users who weren't allowed to use them. It now shows only the actions you can take.
- Users with limited admin access waited on a loading screen in the admin console and it kept making failed requests in the background. It now loads straight away.
- Signing in with SSO and two-factor authentication didn't accept recovery codes. It now does, like the regular sign-in.
- The engagement status control in the page header now appears for everyone allowed to change the status, shows proposed engagements correctly, and explains failures.
- After saving a test case opened from an engagement, Back now returns to that engagement instead of the general test case list.
- AI assistant: error messages are no longer fed back to the model as part of the conversation, a reply can be stopped, and a failed approval now says so.
- Attack graph: nodes you moved no longer jump back when the graph refreshes (e.g. after adding an attacker) or when switching to fullscreen.
- Filtering test cases now shows matching test cases nested under collapsed parents.
- Version history showed wrong relative times ("just now" for hours, or hours off) outside the UTC timezone. Fixed.
- Outside UTC, some dates showed or filtered a day off (scheduling date range, dashboard chart labels, "created after" filters). Fixed.
- Retrying a partly failed evidence upload no longer uploads a second copy of a file that had already succeeded when two files shared a name.
- Images pasted or dropped into an editor could land in the wrong place (even mid-word) if you kept typing during the upload, and were sometimes reported as failed when they hadn't. Fixed.

### Removed
- One-off scripts in `backend/` that were never part of the app and could damage a live install if run: `seed_rbac.py` (`create_all` outside Alembic), `seed_skills.py` (wiped user skills), `seed_test_data.py`, `manual_migrate.py`, `run_migrations.py`, `check_models.py`, `check_tables.py`, `db_diag.py`, `inspect_schema.py`. Default data is seeded at startup; use `migrate.py` for migrations.

## [1.9.1] — 2026-11-16

### Added
- **Sign-in returns you to the page you wanted.** Opening a link while
  signed out, or having your session expire mid-use, now sends you to the
  login page with that page remembered, and you land on it after signing in
  (password, two-factor or SSO) instead of on the dashboard. Only pages
  inside RedWire are accepted as a return target. Signing out on purpose
  still starts you at the dashboard next time.

### Fixed
- **Encryption-key rotation no longer loses data.** `rotate_encryption_keys.py`
  now also re-encrypts auth settings (LDAP / SMTP / SAML secrets), plugin
  settings and spray-result usernames, which it used to skip, leaving them
  unreadable after a rotation. A value encrypted under neither the old nor the
  new key (a wrong old key) is no longer encrypted a second time, which made it
  unrecoverable: a read-only first pass finds such values and stops the run
  before anything is written (`--allow-undecryptable` re-keys the rest and
  leaves them as they are). The rotation steps in the admin guide, the in-app
  help and SECURITY.md named a variable the script never read; they now give
  the real procedure, including stopping the backend and recreating it
  (`docker compose up -d backend`, since `restart` keeps the old `.env`).
- **The AI assistant can no longer read vault secrets.** Every `*_id` tool
  argument must now be a UUID; the vault and cleanup tools' `item_id` /
  `artifact_id` weren't checked, so a crafted id could reach the vault reveal
  endpoint. Viewing, creating or updating a vault item through the assistant
  now hides the username, password and note, as listing already did.
- **Vault: an edited credential no longer shows its old value.** After an
  edit (yours, or another user's once the list refreshes) the revealed,
  copied and edit-form values are fetched fresh instead of served from the
  page's cache.
- **Report layouts: saving no longer overwrites co-editors.** Saving a
  layout's sections now checks it hasn't changed since you opened it. If
  someone else saved in the meantime you're told, and offered their version,
  instead of overwriting their text and deleting the sections they added
  (with those sections' review threads). With no unsaved changes, their
  version is picked up automatically.
- **Link dialog: applying no longer drops intel and infrastructure links.**
  Opening the dialog before its existing intel / infra links had loaded,
  then pressing Apply, unlinked all of them. Apply now waits for them, and
  a failed load skips that type rather than treating it as "no links".
- **Admin → Authentication: a failed load no longer shows a blank form.**
  If the current settings can't be loaded you now get an error and a Retry
  button, instead of an empty form whose Save would replace the real LDAP,
  SAML and splash configuration.
- **SAML sign-in works again.** Every SAML login failed: the replay check
  expected a date where the SAML library hands back a number. With an
  external identity provider the login also failed at the return step,
  because the browser didn't send the request cookie on the provider's
  cross-site POST; over HTTPS that cookie is now sent cross-site.
- **Production now gets its public URLs and optional settings.** The prod
  compose file passed the backend a fixed list of variables, so SAML,
  password-reset and notification links pointed at `localhost`, and settings
  such as `PLUGIN_VERIFY` and the upload size limits had no effect when set
  in `.env`. `BACKEND_URL` and `FRONTEND_URL` now default to
  `https://$DOMAIN_NAME/api` and `https://$DOMAIN_NAME`, and everything in
  `.env` reaches the backend.
- **Password reset and SSO two-factor pages no longer bounce to login.**
  The page guard and the server-side redirect disagreed about which pages
  need no session; both now use one list, and a stale session cookie no
  longer sends the SSO callback or reset-password page to the dashboard.
- **Turning two-factor on (or off) keeps you signed in.** The change signs
  out every session, and it used to sign out yours too, sending you to the
  login page before your recovery codes were shown. You now get a fresh
  session and the codes appear as intended.
- **AI assistant: asset, test case, vault and cleanup creation, and the
  stats tools, work.** The four create tools sent the engagement in the
  wrong place and were always rejected, and `create_asset` didn't ask for
  the required identifier; the two stats tools called endpoints that don't
  exist.
- **Admin → Stats scope mode saves without an error.** The setting was
  saved, but the request then failed, so the page reported an error.
- **Deleting a user no longer breaks other pages or fails.** Test case,
  vault and test-case-template lists failed to load after the person who
  created an item was deleted, and a user who had ever had an API token
  couldn't be deleted at all.
- **PDF reports with filters and the attack graph generate again.** A
  filtered report whose attack graph linked to a filtered-out finding
  failed.
- **Wordlist password checks are accurate again, and NTLM lookups work.**
  After the first wordlist upload on a fresh install the filter behind
  `check-password` filled up and reported every password as found; it is
  now sized with headroom and rebuilt when an upload outgrows it. NTLM
  hashes were stored empty on every import (the server's OpenSSL no longer
  provides MD4), so NTLM lookups never matched; they are computed again, and
  existing entries are filled in by a background job on startup (it resumes
  if interrupted and can take a while on a large wordlist).
- **Many open tabs no longer exhaust the database connections.** Each live
  connection (presence, live notes, live editing) held a database connection
  for as long as the tab stayed open, so a few dozen tabs per worker made
  other requests wait for a free connection. The connection is now released
  once the socket is set up.
- **Sending email no longer stalls the server.** Mail went out on the main
  request loop, so a slow or unreachable mail server held up every other
  request on that worker for up to the SMTP timeouts.
- **Automation rules no longer slow down the change that triggers them.**
  Rules (webhooks, email, notifications) ran inside the request that saved
  the finding, asset or note, so a slow webhook delayed that save by up to
  its timeout. They now run in the background right after the change is
  saved, each limited to `AUTOMATION_TIMEOUT_S` (default 120 s).
- **Generating a report no longer freezes the app for everyone else.** PDF
  and HTML rendering, their evidence-image downloads, and ZIP export
  compression ran on the main request loop. They now run in the background,
  at most two renders at a time per worker (`REPORT_RENDER_CONCURRENCY`).
- **A slow Redis no longer hangs every request.** The session-revocation
  check on each request had no timeout and pinged Redis every time. It now
  uses bounded timeouts (`REDIS_TIMEOUT_S`, default 1.5 s), one round trip,
  and runs off the main loop; if Redis can't answer, requests are refused as
  before.
- **Filtering findings by severity or status works.** `GET /findings`
  accepted `severity` and `status` but ignored them and returned every
  finding.
- **@mentions of dotted usernames reach the right person.** `@john.doe`
  notified the user `john` (if one existed), and e-mail addresses in a
  comment mentioned their domain. Mentions now match the full username and
  ignore e-mail addresses.
- **Cancelling a confirmation dialog no longer leaves the page waiting.**
  Cancel (or Escape) closed the dialog without answering it, so code waiting
  on the answer never continued.
- **The Templates and Runbooks pages update after a create, edit or
  delete.** Their lists stayed stale until a reload.
- **Automation rules on comments, test case execution and team changes
  run.** The "Comment Created", "Test Case Executed", "User Assigned to
  Engagement" and "User Removed from Engagement" triggers were never
  raised. Team changes also now appear in the activity feed per member.
- **Authors can edit their own verified finding.** Any save was refused
  with 403 because the form resends the current status, which was treated
  as the author verifying their own work. Only a real status change is
  checked now.
- **Editing a finding's content withdraws its peer approvals.** Approvals
  used to survive later edits, so a finding could be verified on content
  no reviewer saw. Requested-changes reviews are kept.
- **The edit-engagement page no longer loses unsaved work.** Opening the
  Team dialog or generating phases reloaded the engagement and wiped unsaved
  Details and Timeline edits, switching tabs dropped Skills edits, and Save &
  Close left the page even when the save failed. Failed parts are now
  reported and the page stays open.
- **Engagement export and import keep everything.** Imports used to drop
  classification markings, scoring inputs, custom fields, ATT&CK links, note
  nesting, engagement tags, phases and skills, chain links and peer
  reviews, and broke attack-graph attacker links, saved graph layouts and
  links to specific ports. A tag name used for both findings and
  engagements made the import fail. Peer reviews only carry over for
  reviewers you map to a local user, and a failed import no longer leaves
  uploaded files behind.
- **Importing an engagement credits work to the right people.** The import
  preview showed users as "matched" but credited everything to the person
  importing. Matching users (same account, or same username) are now
  pre-selected in the mapping step, where they can be changed.
- **Exports that couldn't be imported back are refused** with a message
  naming the size setting, instead of producing an archive over the import
  limit.
- **The person importing an engagement is added to its team,** so they can
  open it without admin or view-all access.
- **Exports include inline images, password-spray results, scan import
  history and automation rules.** Imported automation rules start switched
  off so an archive can't set up live webhooks; spray data marks the
  archive as containing plaintext secrets.
- **Deleting no longer leaves half-deleted data or false audit entries.**
  Deleting a test case with sub-cases, or a finding, asset, engagement,
  vault item, cleanup artifact, thread or spray campaign, wrote its audit
  entry first, and writing the entry saved whatever was pending. If the rest
  of the delete then failed, sub-cases were already gone and the log said
  the item was deleted. Audit entries are now written after the change is
  saved, and a failed audit entry can no longer undo the change it records.
- **Blocking work no longer stalls the event loop.** bcrypt (password login, password changes, user creation, recovery-code generation and checks), the *Test LDAP connection* button, SAML response verification and the HTTP log ingester's read-and-parse pass now run in a worker thread. Each bcrypt call held the whole worker for ~100–250 ms; a recovery-code miss for over a second. A test now fails if an async handler calls one of these helpers directly.
- **"One of these" rows are now unique in the database.** The default group, default report theme, default marking profile, an engagement's default layout, intel items per feed link, engagement names (ignoring case and surrounding spaces) and attacker-node edges all get unique indexes (migration `e7a3c1f9b2d4`, which first resolves existing duplicates: the default group with members wins, a user theme beats the seeded one, intel duplicates merge their links into the oldest, and later duplicate engagement names get " (2)", " (3)"…). Before, a duplicate made the code that expects one row fail with a 500: after the default group was renamed, startup re-seeded a second default and user creation broke; a duplicated intel item stopped its feed refreshing for good. Seeders no longer plant a second default, tag and template seeding tolerates same-named rows, intel refresh (now one shared implementation) inserts with `ON CONFLICT DO NOTHING` and clips over-long fields, system widgets seed without racing, re-importing an archive numbers the name ("X (imported) (2)"), and a race past any pre-check answers 409 instead of 500.
- **Emptied fields now actually clear.** Edit forms sent an emptied optional field as `undefined`, which the API reads as "leave unchanged", so clearing it silently kept the old value. They now send `null` (or `""` where the endpoint ignores null): finding text fields, category and CVSS vector; engagement client and end date; phase dates; asset port service/version; infrastructure item fields and vault entries; clients (including unlinking the parent); finding, test-case and layout templates; report theme and runbook descriptions; runbook type; automation rule descriptions; custom-field help text and placeholder. Deselecting all of an asset's ports on a finding (edit page and the engagement page's asset dialog) now clears them; before, the empty selection was never sent. Phase dates and runbook type now treat an explicit null as "clear". A null for a required field (e.g. a finding's title) is a 422 naming the field instead of a 500.
- **Lists no longer stop silently at a page size.** Hooks that feed pickers, charts and per-engagement tabs made one request and got the endpoint's default or cap: the Planning chart 25 engagements, asset/template/runbook pickers 100, users 100, findings and test cases 500. They now page through everything (`lib/fetch-all.ts`). The intel and infrastructure pickers in the link dialogs search on the server instead of filtering their first 200 rows. The asset CSV export requested `limit=10000` (over the 500 cap) and always failed with a 422; it now pages too. List endpoints order with an id tiebreaker so pages don't overlap or skip rows.
- **Planning page: `GET /engagements?include_proposed=true` always returned 500.** A function-local import of `has_global_permission` later in the handler made the name local to the whole function, so the earlier proposed-engagements check raised `UnboundLocalError`.
- **Object storage follows the database transaction.** Uploads (finding / test-case / engagement evidence, vault and infra vault files, intel attachments, inline images, saved reports, scan-import attachments) are tied to the request's transaction: if it doesn't commit, the stored object is deleted instead of staying in the bucket with no row. Single-object deletes (evidence, vault and infra vault files, intel attachments, infra items' files) now remove the object only after the row's delete commits; before, the object went first and a failed delete left a row pointing at nothing. Savepoints (e.g. the activity log's) don't count as commits or rollbacks. Implemented in `utils/storage_tx.py`; `get_db` settles it when the request's session closes.
- **VIEW_ALL_ENGAGEMENTS reads engagements consistently.** A holder (e.g. the Team Leads group) without an assignment could list an engagement's findings, assets and test cases but got 403 opening the engagement itself, its notes, report layouts and cleanup items. The per-engagement check now grants the read permissions in `VIEW_ALL_ENGAGEMENT_GRANTS` (engagement, finding, asset, test case, evidence, discussion, report, note, cleanup). The vault is deliberately excluded and still needs an engagement role with `vault_view`; `/engagements/{id}/my-permissions` used to report `vault_view` for view-all holders, so the UI offered a vault tab the API refused. The unused duplicate checks in `auth/permissions.py` (`has_engagement_permission`, `require_engagement_permission`, `can_modify_resource`) are removed.
- **UI gates match the API's permissions.** The templates page (each tab: finding / test-case templates, runbooks, report layouts, themes, marking profiles), the template edit pages, the marking profile manager and the engagements list's "show proposed" toggle checked for the admin or team-lead role. They now check the permission their endpoints enforce, so a group grant shows the controls and a team lead without one no longer sees buttons that 403. The Planning page's manager view now includes read-only admins, as the focus-fit endpoint does.
- **Refetches no longer wipe in-progress edits.** The evidence description, the profile form, the finding and test-case template editors and the report theme editor copied their record into the form on every refetch (window focus, another save's invalidation, any change to the signed-in user), replacing whatever was being typed. A shared `useFormFromQuery` hook now seeds the form when the record loads and on later refetches only while nothing has been edited (the theme editor seeds once per theme). After a password or email change the profile page signs out through the auth store's `logout`, which also clears the selected engagement and stops the token refresh timer.

## [1.9.0] — 2026-11-11

### Added
- **Hide pages from groups.** Every main-nav page now has a view
  permission, so a page can be hidden from a group by removing that
  permission in Admin → Permissions; without it the tab disappears and a
  direct link is refused. The new permissions are `stats_view`,
  `remediation_view`, `template_view`, `tag_view`, `client_view` and
  `planning_view`, and the sidebar now also honours the existing
  `calendar_view`, `intel_view` and `infra_view`. Upgrading keeps
  everyone's current tabs: the first four are granted to every existing
  group, and Clients and Planning (until now shown to team leads by role)
  to the Team Leads group and any group with a team lead in it. A user in
  no group at all won't see these pages until they're added to one.
  Automations is now in everyone's sidebar, since anyone can make personal
  rules; its Org Rules view needs `automation_view`. The admin guide
  (Help → Admin) lists each page's permission.
- **Backups.** `backup.sh` (in the install directory) backs up the
  database, the MinIO evidence store, `backend/uploads` and `.env`, which
  holds the vault and 2FA encryption keys, into `backups/<timestamp>/`
  (owner-only permissions), keeping the newest 7. The deploy script installs
  it as a daily 03:30 cron job, and now also snapshots the database before
  every upgrade, aborting the deploy if the snapshot fails or the disk is
  too full (`SKIP_BACKUP=1` skips it). Backups on the server's own disk
  don't survive losing the server: set `BACKUP_REMOTE` to an rsync target
  to copy each one off-box.
- **Live editing from the view pages.** Double-clicking a text field on a
  finding, test case or asset page (or its side sheet on the engagement
  page) now opens the same live editor as the full edit page. Everyone
  editing that field sees each other's text and cursors as they type,
  whether they're on the edit page or the view page, and changes save
  automatically, so Save/Cancel becomes Done. Pages showing a record also
  update as others edit it live, instead of only after the first change.
- **Security Center** (Admin → Security) — one place to watch the
  instance's own security. Sign-ins: every successful and failed sign-in
  (with the reason), failed 2FA codes, sign-outs, password and 2FA changes,
  API-token changes, rate-limit hits and SSO errors, with IP and browser,
  plus top failing IPs and most-targeted usernames. Web traffic: every
  request nginx served — the web app as well as the API — with status mix,
  top client IPs, scanner probes (`/wp-login.php`, `/.env`, `/.git/…`),
  scanner and tool user agents, and a searchable request log. Accounts &
  tokens: who lacks 2FA, dormant accounts, risky API tokens, with sign-out-
  everywhere, disable and revoke actions. Posture: a configuration
  checklist (keys, admin 2FA, default passwords, LDAP/SMTP TLS, CORS, TLS
  certificate expiry, …) with fixes. Admin audit: every admin
  configuration change and sensitive action such as vault secret reveals.
  New `view_security_center` / `manage_security_center` permissions
  (read-only admins can view). Retention is configurable (raw web requests
  14 days by default).
- **Upgrading:** redeploy with the new `docker-compose.yml` and
  `nginx/nginx.conf` — nginx now also writes a JSON access log to a new
  `nginx_logs` volume shared with the backend.

### Security
- **Delegated user managers can no longer escalate.** Anyone holding
  `manage_users` without being an admin (Team Leads have it by default)
  could make themselves or anyone else an admin, add themselves to any
  group, or reset an admin's password and sign in as them. They can now
  only assign Operator, Read-Only or their own role, only act on accounts
  that hold no permissions they lack, and only add users to groups whose
  permissions they already have. The duplicate `PUT/DELETE /users/{id}`
  and `POST /users` routes, which skipped these checks, are removed; use
  `/admin/users`.
- **View-only users can no longer change live-edited text.** On the
  live-editing connection for notes and record fields, a user with view
  access only could send a crafted sync message that an editor's browser
  merged and then auto-saved. Those messages are now dropped for
  view-only users.
- **Cleanup artifacts can only be linked within their own engagement.**
  Linking one to a finding, test case or asset from a different
  engagement was accepted and then showed that record's name and
  identifier on the artifact. It now returns 400, like the other link
  endpoints.
- **Restoring a finding version follows the same rules as editing it.**
  It needed only basic edit permission, so a member could rewrite a
  colleague's finding without `finding_edit_any`, or an author could
  restore their own finding to an earlier VERIFIED or CLOSED snapshot and
  skip the separate-reviewer and peer-review rules. Both now apply.
- **Infrastructure vault secrets are no longer sent in the item list.**
  Listing an infrastructure item's vault returned every decrypted
  password and note at once, with no record of who looked. The list now
  shows only whether a secret is set; the value comes from a separate
  reveal request (used by the Show, Copy and Edit buttons), and each
  reveal or file download is recorded in the Security Center.
- **Lists, search and the activity feed respect per-resource view
  permissions.** Engagement roles can withhold e.g. `finding_view` or
  `note_view`, and opening a single finding or note honoured that, but the
  findings, test cases, assets and threads lists, global search, the
  engagement activity feed (which includes note text, finding descriptions
  and comments), the engagement evidence list, and the AI assistant's
  `search` and `get_field_examples` tools only checked membership. They
  now apply the same view permission as the single-item page. The built-in
  roles hold all view permissions, so they see no change.
- **Intel items only show linked records you can see.** An intel item's
  detail listed every linked finding, test case and note by title across
  all engagements, and anyone with `intel_edit` could unlink them. Both
  now require view access to the linked record's engagement.
- **Password changes end API tokens, and reset and 2FA links are single
  use.** Changing or resetting a password (yourself, forced, by an admin,
  or by email link) now deactivates the account's API tokens as well as
  its sessions, as email and 2FA changes already did. A used
  password-reset link, and the short-lived token between password and 2FA
  code at sign-in, can no longer be replayed.
- **Attack-graph edges can only be changed within your own engagement.**
  Edit access on one engagement's attack graph was enough to add or
  delete attacker edges on another engagement's graph, given its attacker
  node id.
- **The backend refuses to start with a weak `JWT_SECRET`.** It used to
  fall back to the default published in the repo with only a log warning,
  so anyone could sign their own admin token. It now stops at startup if
  `JWT_SECRET` is unset, the default, or shorter than 32 characters. The
  production compose file also requires `POSTGRES_PASSWORD`,
  `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`, `JWT_SECRET` and
  `ADMIN_PASSWORD` to be set instead of defaulting to `changeme` /
  `minioadmin`. `deploy_server.sh` already generates all of them.
- **Removed unguarded duplicate group and engagement-role routes.**
  `/admin/groups*` and `/admin/engagement-roles*` repeated the
  `/admin/permissions/...` routes the UI uses, but without the
  permission-grant ceiling or the system/default-group protection, so a
  group manager could, for example, delete the Default group. Use
  `/admin/permissions/groups*` and `/admin/permissions/engagement-roles*`.
- **Removed members can no longer add evidence to findings they created.**
  The test-case upload path was fixed in GHSA-7x2f-ff7r-h388, but the
  finding upload path still let a finding's creator upload after being
  removed from the engagement.
- **A required password change is now enforced by the server.** After an
  admin password reset (or on the first admin login), the "change your
  password" prompt was only a screen overlay: the temporary password
  still worked for every API call and live-edit connection. Until the
  password is changed, the account can now only load its profile, change
  the password, or sign out.
- **Permission ceilings now cover removals and engagement roles.** A group
  manager could only grant permissions they held, but could remove any
  permission from a group or delete any non-system group. Now adding or
  removing a group permission, or deleting a group, requires holding the
  permissions involved. Engagement roles had no ceiling at all: anyone
  with `manage_engagement_roles` could put any permission on any role.
  Editing or deleting a role now requires holding the permissions
  involved in at least one of your engagements. Admins and team leads
  hold every engagement permission.
- **Live editing now follows access changes immediately.** A live-edit
  session (notes, finding / test case / asset text fields, report
  sections) checked permissions only when it connected, so someone
  removed from an engagement, demoted, or deactivated could keep editing
  and saving until they closed the page. Open sessions now re-check
  access every 15 seconds and before every save. Losing edit rights
  turns the editor read-only, and losing view access closes it.
- **Vault file downloads are never rendered.** Downloading a vault file
  also opened it in a new tab on RedWire's own origin, where an HTML or SVG
  file could run script. It is now only saved, as a generic binary, and the
  temporary URL is released.
- **Low-severity permission gaps closed.** Dashboard widgets on spray
  results and comments are now scoped to the viewer's engagements; the
  automation "notify role" action skips members who can't see the event's
  engagement; plugin CMDB / Shodan free-text lookups need asset-create
  permission in some engagement and are rate-limited; activity entries with
  no engagement (2FA recovery-code use, admin settings) are no longer pushed
  live to every logged-in user; and uploading a markdown image into an
  engagement needs a write permission there, not just view.
- **Evidence uploads follow one set of rules.** Replacing an evidence file
  is size-capped and its type comes from the file extension, not the
  client (as on the original upload); engagement-archive import does the
  same and cleans the stored filename; saving a report to an engagement
  needs evidence-create permission, is size-capped and cleans the filename.
  New evidence can no longer be uploaded to, or re-linked into, a VERIFIED
  finding.
- **The backend and MCP server no longer run as root.** Both containers
  run as an unprivileged user (UID 10001) that can write only
  `backend/uploads`. The deploy script hands that directory to the new
  user, and nginx hands it the access log that the Security Center reads.
- **Plugin settings are encrypted at rest.** Plugin secrets such as the
  ServiceNow password and the Shodan API key were masked in the admin UI
  but stored unencrypted in the database. Every plugin setting value is
  now encrypted with the vault key, and existing values are encrypted
  automatically on the first start after upgrading. The Security Center's
  posture check reports any that couldn't be.

### Fixed
- **Saving an asset no longer waits on plugins.** Plugin event handlers
  (such as Shodan auto-enrichment, up to 10 s per lookup) used to run inside
  the save request; they now run in the background, each limited to 30 s
  (`PLUGIN_HANDLER_TIMEOUT_S`). The Shodan enricher's lookup cache now
  expires after 24 hours, so new ports and vulnerabilities show up, and
  holds at most 1,000 hosts.
- **Deleting an engagement that had spray campaigns failed** with a server
  error. The campaigns (and their results) are now removed with it.
- Operations: a backend worker that starts while Redis is down now keeps
  retrying and turns live updates on once Redis is back (it used to stay
  single-worker until restarted); container logs rotate (5 × 10 MB);
  activity pings older than a year and read notifications older than 90
  days are pruned daily (the audit log is kept unless
  ACTIVITY_LOG_RETENTION_DAYS is set); the unused 640 MB wordlist password
  index is dropped and wordlist deletes are indexed; the backend image no
  longer includes uploads, tests or env files.
- Small fixes from the 11/8 review: editing or removing an attack-chain
  link is now in the activity log; restoring a finding version restores its
  scoring model and inputs too (older versions clear inputs that no longer
  match); the engagement picker no longer gets stuck on "new" and is
  cleared at sign-out; the sign-in screen no longer keeps the password in
  memory during the 2FA step; posting in a thread no longer refetches every
  cached finding / asset / test-case list; a SAML sign-in whose username is
  taken or contains odd characters gets a cleaned, unique username instead
  of a server error.
- Read-only admins can download evidence (the download-token step refused
  them) and see an engagement's scan import history.
- Read-only admins and team leads no longer see write buttons the server
  refuses: the permission lists the UI reads now match what the API
  enforces (read-only admins hold view permissions plus explicit grants;
  team leads hold only group-granted global permissions).
- The finding and test-case edit pages no longer discard unsaved changes
  (and silently disarm the leave-page warning) when the record reloads,
  e.g. after a comment or a teammate's edit.
- Live editing keeps working past the 30-minute login-token lifetime: a
  reconnect now refreshes the token first instead of reusing the one the
  page started with, which the server refused, losing pending auto-saves.
- Saving an engagement team with an unknown user or role, or with the same
  user listed twice, now gives a clear error instead of a server error.
- Engagement pages, lists, feeds and deletes are faster on large
  databases: the most-used foreign key columns are now indexed. The
  indexes are built without locking tables, so the upgrade doesn't block
  normal use.
- Large file uploads and downloads no longer freeze the app for everyone
  else on the same server worker while they transfer. Evidence downloads
  now stream instead of loading the whole file into memory first.
- Saving plugin settings twice at the same moment could store a setting
  twice, after which that setting and the plugin's settings page errored.
  Settings are now unique per plugin and key (migration removes any
  existing duplicates, keeping the newest).
- A test case or note can no longer be moved under one of its own sub-items.
  For test cases this made a loop that hung "delete with sub-cases"
  forever; that delete now also stops safely if such a loop already exists.
- Deleting an engagement or a finding now also deletes its stored files
  (evidence, vault files, embedded images). They used to stay in object
  storage indefinitely after the records were gone.
- Deleting a user who had any history (activity, notes, comments, threads,
  templates, registration codes) failed with a server error. Their records
  are now kept with the author shown as a deleted user. Includes a
  database migration.
- After a forced password change, the new session was sometimes signed
  out on its next request. The sign-out-everywhere cutoff and token issue
  times are now compared in whole seconds.
- **A sign-in completed with a 2FA code now fires the `auth.login.success`
  plugin event** — previously only password-only sign-ins did.
- **Plugin events for creates, updates and deletes now fire** — plugins
  subscribed to the documented `<resource>.created` / `.updated` /
  `.deleted` events (e.g. `asset.created`) never received them; they were
  sent under the internal activity names (`asset.created_asset`). Login,
  status-change and report events were unaffected.
- **Sample plugins work** — the Shodan and ServiceNow samples now react to
  new assets, use the asset's identifier (IP / hostname) rather than its
  display name, and their routes work for anyone who can view the asset
  instead of admins only. Shodan's manual enrich no longer errors.
  ServiceNow keeps TLS verification on and can't have its search widened by
  query syntax in the search text. Plugin authors get a startup warning if
  a plugin requires an engagement-level permission for all its routes.

## [1.8.1] — 2026-11-08

### Security
- **Read-only admins can no longer make changes** in a few places that
  still let them: saving or creating report layouts, importing scans,
  linking and unlinking findings / test cases / assets / notes / vault
  items / cleanup artifacts, editing cleanup-artifact links, and managing
  infrastructure vault items. The role can still view all of these, and
  can still edit where an engagement role explicitly grants it.

## [1.8.0] — 2026-11-07

### Added
- **Edit together, live** — the text fields on the finding, test case and
  asset edit pages, and text sections in the report builder, now update for
  everyone on the page as they type, with each person's cursor shown by name.
  Review-comment highlights stay in place while others edit. Fields open
  instantly with their saved text while the live connection starts.
- **Text fields save themselves** — those live fields save a moment after
  you stop typing (and when you leave the page), shown as *Saving…* /
  *Saved* above the field, so text edits alone no longer need Save. Each
  editing session adds one entry to the record's version history and
  activity feed, not one per save. Severity, status and other fields still
  need Save, which keeps review checks, notifications and automations tied
  to it; the "also editing" banner says those are saved by whoever saves
  last. Restoring an old version is refused while someone else has the
  record open for live editing, since their editor would save the old text
  back.
- **Asset version history** — assets now keep versions like findings and
  test cases: see what changed (name, type, identifier, description,
  notes, pwned, in scope) and restore an earlier version from the asset
  page or its edit page. Asset updates in the activity feed show the change.
- **Who's editing an asset** — the asset edit page shows who else is viewing
  or editing it, like findings and test cases.

### Changed
- **Who's here avatars** — your own avatar is always the rightmost; others
  stack to its left, newest furthest left and on top.

### Fixed
- **Blank asset Type on edit** — assets saved with older type spellings
  (`IP_ADDRESS`, `host`, `web_application`…) showed an empty Type dropdown
  when edited. Existing assets are converted to the matching configured type
  (unknown ones become *Other*), and new or edited assets, imports,
  engagement transfers and spray-created hosts always use a configured type.
  The API now rejects a type that matches none, listing the valid ones.

## [1.7.1] — 2026-11-05

### Security
- **Live activity feed identity** — a browser could change the user identity
  on its live-update connection after signing in, and the dashboard's live
  activity feed then delivered events meant for the user it claimed to be.
  Since 1.7.0 gave admins the feed for every engagement, claiming an admin's
  identity exposed activity across all engagements. The connection now keeps
  the signed-in identity; the browser can only say whether it is viewing or
  editing. Upgrade from 1.7.0 promptly.

### Fixed
- **Who's here avatars** — people viewing or editing a page show their name
  and photo again instead of "??", and the "also editing" warning on edit
  pages appears again (both broke with 1.7.0's multi-worker presence).

## [1.7.0] — 2026-11-05

### Added
- **Live updates work across backend workers** — WebSocket events (activity
  feed, notes, discussions, presence avatars, cursors and live note editing)
  now go through Redis, so they reach every user even when the backend runs
  more than one worker or replica. Single-worker installs behave as before,
  and if Redis is unreachable the backend falls back to single-process
  delivery. Set `WS_FANOUT=false` to turn it off.
- **Ready for multiple backend workers** — login and other rate limits are
  now counted in Redis, so adding workers doesn't multiply them. The
  background intel feed refresh runs on one worker at a time. The password
  wordlist filter is kept as one shared copy in Redis, built once instead of
  by every worker. Wordlist imports and deletions apply everywhere
  immediately, and backend restarts no longer rebuild the filter from the
  database.

- **Paste images into templates and intel** — finding, test-case and
  report-layout templates and intel items now accept pasted or dropped
  images. They're stored as shared library images that anyone signed in can
  view, the same people who can see the templates, and they carry into
  findings and reports created from those templates. The new-engagement form
  explains that images can be added once the engagement exists, instead of
  showing an error.
- **"Model not allowed" on the findings list** — findings scored with a model
  their engagement no longer allows are flagged in the engagement's findings
  table and on the Findings page, as they already were on the finding itself.

### Fixed
- **Pasting images into discussion comments** — images pasted or dropped into
  a comment reply now upload instead of failing.
- **Live activity feed for admins** — admins, read-only admins, team leads and
  anyone with *view all engagements* now get live dashboard updates for every
  engagement they can view, not only the ones they're assigned to.

### Changed
- **The backend runs two workers by default** — the production compose file
  now starts two backend worker processes, so one slow request no longer
  holds up everyone else. Set `BACKEND_WORKERS` in `.env` to change the
  number; each worker uses about 200 MB. Enabling or disabling a plugin now
  takes effect on every worker, and startup setup runs one worker at a time.

## [1.6.2] — 2026-11-04

### Fixed
- **Report sections keep their identity on save** — saving a report layout
  used to delete and recreate every section. Sections are now updated in
  place, so their review threads stay attached; removing a section deletes
  its threads. Engagement import keeps report-section threads attached too.
- **Threads left behind by deleted items** — deleting a finding, test case,
  asset, cleanup artifact, evidence file, note or vault item now deletes its
  discussion threads too. They used to stay in the engagement's discussions
  list, linking to nothing.
- **Highlight comments survive engagement export/import** — exported threads
  now include their highlight position, so after an import they still show as
  highlighted comments instead of plain threads.
- **Pasting images into report sections** — pasting or dropping an image into
  a report builder text section failed with "Image upload requires an
  engagement context". The same fix applies to the engagement, asset and test
  case description editors.
- **Scoring policy on the engagement page** — the engagement's allowed and
  default scoring models now offer only the models enabled site-wide, and the
  section is read-only while the site allows a single model. Saving a model
  the site doesn't enable is rejected.
- **Editing findings scored under a dropped model** — a finding scored with a
  model its engagement no longer allows could not be saved at all (any edit
  returned a "not permitted" error). It now saves and keeps its score until it
  is rescored.

### Security
- **Engagement status rules** — non-admins can now move an engagement forward
  any number of stages or back one, put it on hold from any open stage and
  resume to any open stage; Completed is reachable only from Reporting.
  Admins and team leads can still make any change. The edit page greys out
  statuses you can't move to.
- **Approved runbooks are frozen** — approving a runbook snapshots its
  test-case templates, and applying a published runbook uses that snapshot,
  so editing or unpublishing a template later can't change what an approved
  runbook creates. Runbooks already published are frozen at their current
  content on upgrade; editing a published runbook's items refreezes them.
- **New default permissions reach existing installs** — permissions a release
  adds to the default groups and roles are now granted once to existing
  deployments (tracked by a seed revision), instead of reaching only fresh
  installs. A grant an admin later removes stays removed. This release grants
  Team Leads *manage marking profiles*, Engagement Lead *evidence edit* /
  *evidence edit any*, and Operator *evidence edit*.
- **Deleted-engagement audit logs** — a new Admin → Audit tab lists deleted
  engagements with their surviving activity history (who did what, when),
  previously reachable only from the database. Visible to admins, read-only
  admins and anyone with *view all engagements*. Engagements deleted before
  this release show only their deletion record.

### Added
- **httpx and NetExec (nxc) scanner imports** — the scanner import now accepts
  httpx JSON/JSONL output (hosts, web ports, server, page titles and
  technologies) and NetExec console or `--log` output (hosts and services
  from nxc's host banners). NetExec flags become findings: SMB signing not
  required, SMBv1 enabled, SMB null sessions and RDP without NLA. Credential
  results are left to the Spray import, and passwords in a logged command line
  are masked.
- **Classification banner on engagements** — engagements with a marking
  profile show a banner across the top of the engagement page with their
  default level in its colors, plus the profile and ceiling.
- **Review threads on report sections** — report builder sections now support
  the same peer-review comments as findings. In a saved text section, select
  text to leave a highlighted comment. Every section also has a "Review
  threads" list, collapsed by default, for general discussion; the
  all-sections view shows each section's open-thread count. Mention
  notifications link straight to the section.
- **Marking column on the engagements list** — shows each engagement's
  marking profile; hover it to see the profile's levels.
- **"Model not allowed" indicator** — findings scored with a model their
  engagement no longer allows show a warning on the finding page, the finding
  side panel and the edit page, which explains how to rescore with an allowed
  model.

## [1.6.1] — 2026-10-29

### Security
- **Interactive HTML report: stored XSS** — finding titles, asset names, CVSS
  vectors, cleanup-artifact fields and attack-graph labels were inserted into
  the interactive HTML report without escaping, so markup in any of them (typed
  by a user or carried in from imported scanner output) ran as script when the
  report was opened. Every such field is now escaped. Affects HTML reports
  generated since the interactive report was introduced; regenerate any HTML
  reports you have shared.
- **Request size caps** — the scoring-policy settings, attack-chain link and
  AI-chat mode fields now enforce maximum lengths like every other request
  field.

### Changed
- **Severity colors** — the remediation tracker, report-builder pickers and
  threat-intel severities now use the shared severity palette too.

### Fixed
- **Burp and Nessus imports** — on public installs the Burp and Nessus parsers
  failed to load, so uploading either scan format errored; a finding whose
  creator had been deleted could also fail to display. Both fixes were in the
  development tree but had not reached the public release.

## [1.6.0] — 2026-10-29

### Added
- **Pluggable finding scoring** — findings can be scored with rating models
  beyond CVSS 3.1. A **Scoring Model** picker on the new and edit finding pages —
  and inside the double-click score editor on the finding view page and the side
  sheet — lets you choose a model; the calculator renders that model's metrics
  (selects and 0–N button scales) and computes the score and severity live.
  Built-in models:
  - **CVSS 3.1** — the existing base-score calculator.
  - **DREAD** — mean of the five 0–10 factors.
  - **OWASP Risk Rating** — Likelihood × Impact from their factor groups, via the
    OWASP severity matrix.
  - **USAF Risk Assessment Matrix** — MIL-STD-882 hazard Severity (I–IV) ×
    Probability (A–E) → Extremely High / High / Medium / Low.
  Every model maps onto the existing Critical/High/Medium/Low/Info scale, so
  dashboards, reports, analytics and automation are unaffected. The rating is
  recomputed on the server when a finding is saved, so it is always authoritative,
  and each finding remembers which model and inputs produced it.
- **CVSS 4.0 scoring (plugin)** — a bundled **CVSS 4.0 Scoring** plugin adds
  CVSS 4.0 (CVSS-B) as a scoring model. It appears in the Scoring Model picker
  like the built-ins; its engine is a faithful port of FIRST.org's reference
  calculator (validated to match exactly across 25,000 vectors). Plugins can now
  contribute scoring models — a declarative model definition plus, for complex
  math, a scoring engine — through the plugin system.
- **Scoring-model policy** — admins choose which scoring models are enabled
  site-wide, the default model, and optionally lock every finding to a single
  model (**Admin → Policies → Scoring models**). Each engagement can narrow that
  further with its own allowed models and default (**Edit engagement → Scoring
  policy**). The model pickers only offer permitted models and lock when just one
  is allowed, and the server rejects a finding scored with a disallowed model.
- **Admin Policies tab** — site-wide policy settings (stats scope, peer review,
  scoring models) now live together on a new **Policies** tab in the admin area.
- **Model-aware score display** — reports (PDF, HTML, Markdown) and the finding
  view, side sheet and remediation tracker label each finding's score with the
  model that produced it instead of a fixed "CVSS 3.1". Categorical models show
  their outcome (e.g. USAF "Extremely High") rather than a number, the HTML
  report's metadata lists the scoring models used, and JSON exports include
  each finding's `score_model` and `score_inputs`.
- **MCP: scoring models** — `create_finding` and `update_finding` accept
  `score_model` + `score_inputs` (the server computes the rating), and new
  `list_scoring_models` / `get_scoring_model` tools let MCP clients discover the
  models an engagement permits and their metrics.

### Fixed
- **MCP `create_finding` always failed** — the tool sent `engagement_id` only
  as a query parameter, but the API requires it in the body, so every call was
  rejected; its schema also omitted the required `description`. Both fixed.
- **Let's Encrypt renewals not taking effect** — the certbot container renewed
  certificates on schedule, but nginx kept serving the old certificate from
  memory until it was restarted, so the site's certificate expired despite a
  valid renewal on disk. The production nginx container now reloads every 6
  hours to pick up renewed certificates.

### Changed
- **Consistent severity colors** — severity badges, accents and charts across
  findings, test cases, assets, imports, the attack graph, analytics and client
  stats now share one palette (Critical red, High orange, Medium yellow, Low
  light blue, Info slate). Previously some views showed Medium as amber and Low
  as a darker blue.
- **New finding page: Custom Fields tab** — custom fields moved from the sidebar
  into a **Custom Fields** tab in the main editor, matching the edit page. The
  tab only appears when finding custom fields are defined.

## [1.5.7] — 2026-09-21

### Added
- **Anchored peer-review comments** — highlight a span of text inside a finding or
  test-case field and attach a review thread to it, Google-Docs style. Double-click
  a field (or its comment-count chip) to open annotation mode: an editor with the
  review highlights beside a comments panel. Select text → **Add comment** anchors a
  thread to that span; highlights track edits live and re-anchor on save, and a
  comment whose text is later deleted is flagged **Outdated** rather than lost.
  Works on every text field of findings and test cases, on the detail pages, the
  side sheets, and the full edit pages. Reviewers who can view a finding can comment
  even without edit rights. Available across the app since it's built into the
  shared editor.
- **Peer review ties into comments** — leaving an anchored comment on a finding
  automatically records your peer review as *changes requested* (the author is
  skipped). Anchored review threads are titled `<Field> Review #N`.
- **Attack graph on finding & test-case pages** — a collapsible **Attack Graph**
  section on the finding and test-case view pages shows that item's attack path:
  the chain that led to it (upstream) and what it produced downstream, with the
  same interactive controls as the reporting page (drag to connect, edit/delete
  edges) so chains can be built and edited right from the view page.
- **Tags column on the findings & test-case tabs** — an optional **Tags** column
  (hidden by default; enable it from the column toggle) shows each row's tags.

### Improved
- **Reports draw the attack path from your authored chains** — the PDF and
  interactive HTML reports now build each finding's attack path from the causal
  chains you author in the app (falling back to the test-case→finding→asset
  associations when a finding has no chain), so what you edit in the attack graph
  is what the report shows. The reporting page's attack-graph selector now picks a
  **finding** to view its chain (instead of an auto-detected cluster).
- **Result counts by the search bar** — the finding, test-case, asset, attachment,
  vault, cleanup and notes tabs (and the clients, tags, template and test-case
  list pages) now show a live "N results" count next to the search box, in a
  fixed slot so the controls don't shift as you type.
- **Clickable attachments in tab tables** — linked evidence in the Links column of
  the finding/test-case tables now opens the attachment view page, like linked
  findings and test cases already did.

### Improved
- **Annotation editor UX** — the comments panel is resizable (drag its edge) and
  collapsible; the editor keeps its own vertical resize grip; the "Add comment"
  button and composer now sit over the editor near your selection instead of
  drifting off-screen. Comments render Markdown, show the author's avatar (hover for
  the name), and a header toggle hides resolved threads (resolved threads also drop
  their highlight). Thread/comment delete controls were added to the panel.
- **Cleaner discussion section** — the resource's discussion area is now titled
  **Peer-review comments**, collapses from its title, keeps the anchored ("highlight")
  threads hidden behind a toggle to stay focused on general discussion, and shows the
  anchored field + quote for context. Thread/comment counts moved onto the title row.
- **Two-row editor toolbar** — the formatting toolbar no longer wraps: everyday
  controls stay on the primary row and the lesser-used ones (underline, highlight,
  colour, sub/superscript, alignment, task list, blockquote, Mermaid, table) move
  behind a **More** toggle (remembered per user). Applies everywhere the editor is used.
- **Collapsible right pane** on the finding and test-case detail pages — collapse the
  Risk Assessment / Test Details sidebar to give the main content full width (a slim
  "Details" tab brings it back; remembered per view). The Execution Result section on
  the test-case page is now collapsible too.
- **Tighter, more consistent detail pages** — reduced the heavy section padding and
  normalized section-title sizing on the finding/test-case view pages, and gave the
  finding's Executive Summary the same boxed style as Technical Analysis.

### Fixed
- **Edit pages: sticky tabs & sidebar** — on the finding/test-case edit pages the tab
  bar now stays pinned below the header while the sections scroll, and the right
  sidebar pins at the correct offset instead of sliding under the header.

## [1.5.6] — 2026-09-09

### Security
- **New users no longer get platform-wide engagement visibility by default** —
  `VIEW_ALL_ENGAGEMENTS` was removed from the built-in **Default** group (it
  grants view of *every* engagement's findings/assets/vault/etc. and proposed
  engagements). New users now see only the engagements they're assigned to;
  grant `VIEW_ALL_ENGAGEMENTS` via the Team Leads group or explicitly for a
  cross-engagement viewer. (Existing installs: remove it from the Default group
  in Admin → Permissions to apply.)
- **Closed several endpoints that skipped their permission check** — a permission
  audit found endpoints that returned or changed engagement data for any signed-in
  user, regardless of assignment: the finding remediation summary, per-asset
  remediation toggle, reading/resolving discussion comments, linking test cases to
  findings/assets, reading engagement phases, and the ATT&CK coverage/Navigator
  exports. They now enforce the matching finding / test-case / discussion /
  engagement permission, and the dashboard "computed metrics" are scoped to the
  caller's engagements like the rest of the stats.

### Changed
- **Permission consistency (assignable, not role-hardcoded)** — user, group,
  engagement-role, and registration-code management; finding/test-case templates,
  runbooks, report themes/layouts; and engagement creation now enforce their
  assignable permissions (grantable via a group) instead of a hardcoded admin/lead
  role. The **Team Lead** role remains a blanket bypass for *engagement* work;
  platform-wide management now comes from **group permissions** (the admin
  edit-user dialog now explains this). Read-only admins keep read access to RBAC
  config but can no longer perform these writes.
- **Removed the unused "Customize Dashboard" permission** — it was defined and
  grantable but never enforced (personal dashboard layout is available to every
  user regardless), so it's gone from the permission list.
- **More admin surfaces are now delegatable** — configurable types, marking
  profiles, and custom-field definitions gained assignable permissions
  (`manage_configurable_types`, `manage_marking_profiles`, `manage_custom_fields`)
  instead of being hardcoded admin-only; engagement **import** now uses the
  `create_engagement` permission and the **proposed-engagements** views use
  `view_all_engagements`. Wordlist hash lookup/check stays open to any operator by
  design (it's a core capability, like the password-change bloom check).
- **Admin console is permission-gated per tab** — a user with a delegated
  management permission (e.g. custom fields, taxonomy, skills, widgets) now sees
  the **Admin** link in the sidebar, can open the Admin area, and sees only the
  tabs they can manage, instead of the whole console being restricted to the
  admin roles. Within the Operators tab, the create/edit/delete controls only
  appear for users with `manage_users`. Admins/read-only admins still see
  everything.

### Added
- **Peer review for findings** — operators can now review a finding and record an
  **Approve** or **Request changes** verdict from the finding's sidebar
  (discussion stays in the finding's comment threads). A new admin policy
  (**Admin → Permissions → Finding peer
  review**) can require a configurable number of independent approvals before a
  finding may be marked **Verified**. When required, the verify action is blocked
  (for everyone, including team leads and admins) until the threshold is met; a
  finding's author can never approve their own work. The sidebar shows approval
  progress, who reviewed, and how many more approvals are needed.
- **Effort / time-on-task metrics** — the Analytics page now shows estimated
  active time per work type (findings, test cases, assets, notes), derived from real
  editing activity (the visibility+interaction-gated heartbeat now records which
  record you're working on) and bucketed into sessions. Aggregated and
  anonymised — totals and contributor counts only, never per-person.
- **Edit text attachments in-app** — text files (`.txt`, `.md`, `.log`, …) now
  have an "Edit Text" action that turns the preview area into the editor in place
  (no popup) and saves back over the attachment, alongside an inline text preview.
- **Edit CSV attachments as a table** — CSV attachments render as a
  spreadsheet-style grid (row numbers, column letters, add/delete rows &
  columns) for both preview and edit-in-place.
- **Editor line numbers + active-line highlight** — a toolbar toggle adds a
  numbered gutter to the editors (finding/test-case/note fields and the notes
  tab) and highlights the line the cursor is on.

### Improved
- **Half-view side sheets now show (and edit) almost everything the full page does** —
  the quick-look side panels for findings, test cases, and assets were missing a lot
  of detail; they've been brought close to parity with their full pages. Findings
  gained peer review (and the same gate blocking Verified until approvals are met —
  previously the sheet could bypass it), discussion + remediation threads, affected
  targets with per-asset remediation/progress/ports, evidence, steps to reproduce,
  references, and a full CVSS vector with copy. Test cases gained execution recording
  (pass/fail/actual result), their own notes field, discussion, and an evidence
  gallery. Assets gained discussion, port service versions, and clickable
  cleanup/vault links. All three now support inline quick-edit (title, status,
  severity/type, category, tags, and the markdown fields) right from the sheet, plus
  reviewer presence and live refresh — no need to open the full page for routine edits.
  Each section in these sheets is collapsible (defaults matching the full page), so
  the narrow panel stays manageable.
- **Condensed the "Linked Resources" panel** — on the finding and test-case detail
  pages and their side-sheet ("half") views, the linked items (test cases,
  findings, assets, vault items, cleanup artifacts, notes, intel, infrastructure)
  now flow in one tight list under a single header instead of a titled sub-section
  per type. Each item's colored icon identifies its type, saving a lot of vertical
  space.
- **More pages update live** — finding/test-case/asset/attachment **detail**
  pages now refresh in place when a teammate edits the record (previously they
  showed the teammate's presence but stale content), the Operations Analytics /
  stats page refreshes on tracked changes instead of only on load, and the
  Infrastructure page updates live when items change. Redundant fallback polling
  was trimmed (admin user list 15s→30s, notifications 60s→300s) now that these
  are WebSocket-driven.
- **Accurate online/active indicators** — a user's "active" status is now driven
  by real activity (a heartbeat sent only while the tab is visible and the user
  has interacted recently) instead of any authenticated request. An idle tab left
  open — or a backgrounded tab — no longer shows the user as online; they age out
  once they stop interacting.
- **Search & filters on the admin user list** — the Operators tab gained a search
  box (username / email / name) and a filter popover (role, status, online-now,
  group), with an active-filter count and clear-all.
- **Notes open without the load pause** — the collaborative notes editor shows
  the note's content immediately (an instant preview while it connects, and no
  peer-sync wait when you're the only one on the note) and syncs in the
  background, instead of a ~1s "Loading note…" pause on every open.
- **Activity feed shows what changed in a note edit** — an edited note now
  renders a diff of just the changed lines (with a little context) instead of a
  bare "edited note content" line or the whole note.
- **Warn before editing a locked attachment** — opening the image/text/CSV
  editor on an attachment whose parent finding is VERIFIED now warns up front
  (the chain-of-custody lock would reject the save) so you can back out early.
- **Vault table view keeps the crack / wordlist actions** — the row action menu
  in the vault table now offers "Check Wordlist" and "Crack Hash" (for
  hash-shaped credentials), matching the card view.
- **Import source files are kept on record** — scanner imports and asset imports
  now auto-save the uploaded file to the engagement as an attachment (excluded
  from the report), and password-spray logs are auto-saved to the engagement
  vault (encrypted at rest, since they contain credentials). The upload screens
  note this.

### Fixed
- **Disabled plugins stay disabled after a restart** — the plugin loader now
  reads the saved enable/disable state at boot, so a plugin an admin disabled no
  longer re-enables itself when the containers restart or rebuild.
- **Tree view: drag a sub-test-case back to the top level** — in the Test Cases
  tab tree view you could drag an entry *onto* another to nest it, but there was
  no way to un-nest a child. Dragging now reveals a "Drop here to move to the top
  level" zone, so a child can be pulled back out to the root.
- **PDF report crash on some markdown content** — a field containing an
  identifier with an underscore or asterisk that appeared both in an emphasis
  span and in inline code (e.g. a service account like `svc_backup2` shown both
  in italics and in a `code` sample) could produce overlapping tags that crashed
  PDF generation with a 500. Inline markdown now renders such content safely.

## [1.5.5] — 2026-08-30

### Added
- **Interactive HTML report** — the HTML report format is now a portable,
  offline, self-contained interactive report: an Overview dashboard (risk
  posture, severity mix, key metrics, exposure-by-asset), filter/search/sort
  findings, a hierarchical test-case view, a **live attack graph** (with a
  per-finding "attack path"), an evidence gallery, and cleanup triage — all in
  three audience lenses (Executive / Security / Developer). It's a single
  `.html` file with everything embedded (data, images, fonts), so it opens by
  double-click and renders fully offline. Design spec + clickable prototype
  under `docs/report-redesign/`.
- **AI writing assistant in the editor** — an "Ask AI" panel on finding,
  test-case, asset, engagement, and note fields helps draft or edit the field
  you're on. It's grounded in the record (title, severity, CVSS, status), can
  look up how the same field reads in your other findings to match their style,
  and stays scoped to that one field rather than producing a whole write-up.
  Highlight text first and it rewrites just the selection (with a one-click
  "Replace selection"); otherwise it inserts at the cursor.
- **Readability review** — a **Review** button checks the current field for
  AI-slop and readability and returns concrete, field-scoped fixes (it never
  rewrites the field for you), using a bundled writing-review skill.
- **AI assistant on notes** — the collaborative notes editor gains the same
  Ask AI + Review assistant (hidden for read-only viewers).

### Improved
- **PDF report front-page dashboard + attack graphs** — the PDF now opens with a
  Risk Overview page mirroring the interactive report: the overall risk rating,
  a severity donut, key-metric tiles (findings / assets / test cases / fixed), a
  severity legend, and an exposure-by-asset chart. Each finding also carries an
  **attack path** diagram (test cases → finding → assets → cleanup), and small
  engagements get a full-engagement **attack graph** section. All rendered
  natively — no new dependencies.
- **Richer test cases in the PDF report** — the flat 4-column test-case table is
  replaced by a hierarchical detail view: the parent → child test tree, a
  pass/fail status chip, and markdown-rendered steps / expected result / actual
  result / notes, plus the findings each test discovered.
- **Resizable editors** — drag the bottom corner to resize the whole editor,
  and an inner handle to rebalance the editor against the AI panel without
  changing the overall size. AI replies now render as formatted markdown, and
  the assistant shows live "thinking" and data-lookup indicators.
- Editor toolbar icons now all have hover tooltips.
- **Paste a link onto selected text** — pasting an `http`/`https`/`mailto` URL
  while text is selected now turns the selection into a hyperlink instead of
  replacing it.

### Security
- **Template usage-counter endpoints now enforce the template visibility gate** —
  `POST /{template_id}/use` (finding + test-case templates) previously bumped the
  counter keyed only on the id with no visibility check, letting any authenticated
  user increment (and existence-probe via 200-vs-404) another user's non-published
  draft. It now 404s a template the caller can't see, like every other read.

## [1.5.4] — 2026-08-26

### Added
- **Record a test-case result without a pass/fail verdict** — the execution flow
  gains a "No Verdict" option that marks the case executed while leaving the
  pass/fail result unset, for logging an actual result without asserting an
  outcome. Shown as "Executed / No verdict" throughout. A separate **Save**
  action logs the actual result without changing the execution status at all,
  for recording incremental work before deciding an outcome.
- **Search assets by port version** — the asset search now supports a `version:`
  token (e.g. `version:8.2`) and free-text over ports, so typing a service name
  or version string (`OpenSSH 8.2`, `Apache`) finds the asset by its port.
- **Filter by tags** on the findings and test-case tabs and the engagements
  list — a searchable, colour-coded tag multi-select in the advanced-filters
  panel (the filter icon). Engagement tag filtering is server-side so it works
  with pagination.
- **Category filter** on the findings and test-case tabs is now a searchable,
  colour-coded dropdown built from the categories actually in use (replacing the
  test-case checkbox grid; findings had no category filter before).
- **Asset filters** — the Type filter is now a searchable colour-coded dropdown
  (type badge + icon), and Created By is a searchable dropdown of the assets'
  creators with profile-photo avatars (replacing the checkbox grid and the
  free-text box). The asset search bar is also wider.
- **Filter the activity feed by specific items** — a new searchable multi-select
  on the activity feed lets you scope the stream to one or more specific
  findings, test cases, assets, or notes (in addition to the existing filter by
  resource type).
- **Activity feed filters are now searchable multi-selects** — the Type, Action,
  and User filters use a consistent searchable dropdown; Action and User (which
  were single-select) can now scope to several actions or several users at once.
  The Type filter is colour-coded per type and the User filter shows profile
  photos.
- **Activity feed date range** collapsed into a single calendar button with
  quick presets (Last 7 / 30 / 90 days, Last year) plus a custom from/to range.
- **Inline field editing on the test case and asset view pages** — extends the
  double-click-to-edit behaviour introduced for findings in 1.5.3 to test cases
  and assets. Test cases: title, description, execution steps, expected result,
  notes, category (searchable, colour-coded), and tags (multi-select dropdown).
  Assets: name, identifier (with a copy button), asset type (searchable, colour-
  coded), description, and notes. Each saves a single-field patch; editor-only,
  with an "add" affordance on empty optional fields.

### Improved
- **Test-case execution result** section restyled to match the app's theme (soft
  tinted Pass / Fail / No-Verdict buttons, a state-coloured result card), with
  tooltips explaining that pass/fail means the actual result matched — or didn't
  match — the expected result.

### Fixed
- **Dashboard chart tooltips** no longer run off the bottom of the page for
  widgets low on the dashboard — the hover tooltip is clamped to the chart so it
  stays on-screen.
- **Test case Notes section** now starts collapsed on the view page (expand to
  read/edit), so it no longer pushes the rest of the page down by default.
- **Long titles no longer force a horizontal scrollbar** on the findings, test
  cases, and assets tab tables — the title column now truncates with an ellipsis
  (full text on hover), scaling up on wider/higher-res screens before it
  truncates.

## [1.5.3] — 2026-08-26

### Added
- **Inline field editing on the finding view page** — double-click a field to
  edit it in place and save, without opening the full edit page. Works for the
  title, the markdown fields (description, impact, steps, technical details,
  mitigations, references), severity, category (searchable, colour-coded), tags
  (multi-select dropdown), and CVSS (opens the calculator, auto-syncs severity).
  Editor-only; empty optional fields surface an "add" affordance. (Test case +
  asset pages to follow.)
- **Link attachments to a finding or test case** from the Attachments tab — a
  new "Link to…" row action opens a searchable single-target picker (with a
  "Not linked" option to clear). The backend enforces the single-target rule
  (a finding *or* a test case, not both), same-engagement scoping, and the
  chain-of-custody guard (attachments on a VERIFIED finding can't be moved).
- **Team Lead role** can now be assigned from Admin → Users (create and edit),
  alongside Operator / Read-Only Admin / Admin — the edit dialog now uses a
  single **Platform Role** dropdown.

### Improved
- **Attack graph now shows the test-case hierarchy** — parent → child
  (`subtest`) edges from the test-case tree are drawn (dashed, distinct from
  causal chain edges), so a hierarchical chain like "Test web app → Test auth
  → Test JWT sig → finding" reads as one connected path even when the
  intermediate parent test cases produced no findings of their own.
- **Collaborative notes editor** now shows a loading spinner ("Loading note…")
  while it connects and syncs, instead of a blank content area, and paints the
  note faster: the DB-content fallback debounce dropped from 800ms to 300ms, so
  a single user opening a note no longer waits on a fixed peer-sync window that
  will never fire.
- **ATT&CK AI auto-suggest** now works on the **test cases** sub-tab too (not
  just findings), and both sub-tabs gained an **"Include already-tagged"**
  toggle to re-suggest techniques for items that already have ATT&CK mappings.
  The suggest controls only appear when AI is configured on the instance.
- **Intel & Infrastructure linked-entities lists** now scale cleanly — because
  these are global items that can accumulate many links, the detail panels cap
  the list height with an internal scroll, add a filter box past a threshold,
  and collapse to the first few rows with a "Show all N" expander instead of
  rendering an unbounded list that overflowed the dialog.

### Fixed
- **Notification email in Outlook** — switched the email accent from the
  off-brand indigo-purple to the RedWire brand red, and render the CTA as an
  Outlook VML button so its red fill + white label survive Outlook's dark-mode
  colour transform (which previously repainted the button blue with a darkened,
  hard-to-read label). Other clients keep the CSS rounded button.
- **Cleanup actions menu** — the cleanup artifacts table now always shows the
  row actions (⋮) menu, instead of hiding it until hover, matching the
  findings / test cases / assets tables.
- **Editor hyperlinks** — typing (or a space) after a link no longer extends
  the hyperlink onto the new text, and clicking the link toolbar button while a
  link is selected now removes it (toggle off).
- **Report/download filenames with non-ASCII characters** no longer error when
  generating a report (or exporting an engagement) whose name has accented or
  non-Latin characters. Downloads now use an RFC 6266/5987 dual filename
  (ASCII fallback + UTF-8 `filename*`), so the real name renders and the header
  never fails to encode.
- **Admin users table** now shows each user's real platform role (Operator /
  Team Lead / Read-Only Admin / Admin / Read-Only) instead of labeling everyone
  who isn't an admin as "User".
- **Analytics 403 for Team Leads** — the stats/analytics scope check now honors
  a group-granted `view_all_engagements` permission (the standard 3-tier gate),
  so a user in a group with platform-wide view access can see any engagement's
  stats instead of getting a spurious 403.
- **Entity linking gaps** — the link-items action now offers every supported
  relationship consistently: the **Findings tab** can link **test cases**; the
  **Assets tab** can link **findings** and **test cases**; the finding detail
  view now actually links **assets** (the tab showed but did nothing); and the
  asset detail page now actually links **vault items** (same silent no-op).

## [1.5.2] — 2026-08-25

### Improved
- **Test-case Notes** — a test case's notes now render in a dedicated collapsible
  **Notes** section (above Evidence) through the Markdown viewer, instead of as
  plain text tucked in the sidebar.
- **Collapsible sections** on the finding and test-case view pages — every
  main content section (Executive Summary / Technical Analysis / Mitigation /
  References on findings; Description / Steps / Expected Result / Notes on test
  cases) now has a collapse toggle, and the **Evidence** section starts
  collapsed.

### Fixed
- **Cleanup tab badge** now shows the **total** number of cleanup artifacts,
  matching the other engagement tab badges, instead of only the count still
  pending.
- **ATT&CK AI suggestion** now honors the admin **AI TLS-verify** toggle, so
  technique auto-suggest works against a self-hosted AI endpoint with a
  self-signed certificate (it previously always verified).
- **Test-case category dropdown** now populates from the admin-configured
  dynamic test-case types (like findings/assets do) instead of a hardcoded
  list, on both the new- and edit-test-case pages.
- **Tags are now scoped per entity type** — a tag belongs to findings, test
  cases, OR engagements, so the Tags page tabs (and each picker) only show the
  relevant tags instead of one shared pool leaking across all tabs. Existing
  tags are kept and assigned to the type they were used with most.
- **Notes editor styling** — the collaborative notes editor (engagement Notes
  tab) now shares the standard editor's rendering styles, fixing **code blocks**
  (syntax highlighting / dark code theme) and **task-list checkboxes** (the
  themed indigo checkboxes) that had drifted out of sync and rendered unstyled.
- **PDF report generation** no longer crashes when a finding field contains a
  large markdown block (e.g. a code block taller than a page). Finding content
  now flows and paginates across pages instead of being forced onto one page,
  and long fields are no longer silently truncated.

## [1.5.1] — 2026-08-23

### Fixed
- **Notes** — the "Updated" timestamp on the notes tab no longer always reads
  "just now"; the time is now parsed as UTC (viewing a note never changes it).
- **Notification emails** — the call-to-action button now renders correctly in
  **Outlook** (padding/background moved onto the button cell), and the dark
  template now **stays dark** in dark-mode clients instead of being auto-inverted
  into an unreadable light-on-light state (declares `color-scheme: dark` and
  locks its surfaces with `bgcolor`; Apple Mail / iOS / Outlook honour this —
  Gmail still applies minor shifts but stays readable). The admin **Send test
  email** now uses this same template so you can preview it in your own client.
- **Activity feed — note edits** now show a **field-level diff** (what changed
  in the title/content) instead of dumping the entire note on every update,
  matching how finding and test-case edits already render. New notes still show
  their full content.

### Added
- **Template usage analytics** — finding and test-case templates now track how
  many times they've been applied. Each apply from the "Select a template"
  picker increments a usage counter; the picker and the Template Library both
  show the count and can **sort by most used** (a "Popular" toggle in the
  picker, a sortable **Used** column on the Templates page) — so you can see
  which templates actually get used.
- **Runbook usage analytics** — runbooks now track how many times they've been
  **applied to an engagement**, shown as a sortable **Used** column on the
  Templates page. Applying a runbook also counts a use for each test-case
  template it materializes, so template popularity reflects runbook applies too.

## [1.5.0] — 2026-08-20

### Improved
- **Notification emails redesigned** — per-user notification and automation
  emails now use a professional, branded template: the RedWire logo (embedded
  inline so it renders in every client), the dark theme with the indigo accent,
  a category badge, a details table, and a clear call-to-action button.
- **Friendly names everywhere** — the UI now shows a user's full name (falling
  back to their username) instead of the raw username, with the `@username`
  shown on hover. Applied across creator labels (findings, test cases, assets,
  cleanup, evidence, scan imports), the activity feed & logs, comments,
  notifications, and user pickers; avatar initials now use the full name too.
- **Planning inspector** — the selected engagement's team is now grouped by
  **engagement role** (Leads first, then other roles, unassigned last) instead
  of one flat list.
- **Command palette discoverability** — the global search dropped the misleading
  "Ctrl+K" hint (that shortcut opens the command palette, not the search). A VS
  Code-style **">" button** to the right of the search now opens the palette;
  Ctrl/⌘ K still opens it too.
- **Apply-template picker** — the "Select a template" modal now searches and
  pages the **whole** library on the server (debounced live search), replaces
  the crowded category chips with a funnel filter icon that reveals a
  **multi-select searchable category filter**, colors each result's category
  badge by its type (click a badge to toggle that category), and is wider.
- **Template editing** — the finding- and test-case-template edit pages now use
  the sticky bottom **"Unsaved changes"** save bar (Discard / Save) that appears
  only when there are edits, matching the finding editor, plus a navigation
  guard that warns before you leave with unsaved changes.
- **Engagements search** is now debounced (300ms), firing one request after you
  pause instead of one per keystroke — matching the Template Library search.
- **Template Library** — finding, test-case, and runbook lists are now
  **server-paged** with page controls, and search / status / category /
  "mine only" filters query the **full** library on the server (live search)
  rather than only the first 100 rows the page had loaded.
- **Client picker** — assigning an engagement's client now uses a **searchable
  list of existing clients** everywhere: the engagement overview Client card
  (available even when no client is set yet — previously the card and its edit
  button were hidden), and the new-/edit-engagement forms (replacing the plain
  dropdown).
- **Notifications popup** — hover a notification (bell icon) to read its full
  title and message in a tooltip, instead of the truncated preview.

### Fixed
- **Infrastructure** — infrastructure items can now be **edited** from the
  Infrastructure page (an Edit button on each card opens the create/edit dialog
  pre-filled). The update API existed but had no UI.
- **Template preview** — the finding/test-case preview modal now shows all
  content fields: findings gained the missing **References** and **Attack
  Techniques** sections, test cases gained **Attack Techniques**. All text
  fields render through the Markdown viewer.
- **Automations** — a "finding status changed" rule (e.g. "when a critical
  finding is marked Verified") no longer fires when a finding is first
  **created**, or when a finding is edited without changing its status. The
  status-change triggers now fire only on a real status transition. (This also
  enables the engagement/cleanup status-change triggers, which previously never
  fired.)
- **Notifications popup** — relative timestamps no longer always render "just
  now"; the created-at time is now parsed as UTC.
- **What's New modal** no longer reopens on every page navigation. It now only
  surfaces released entries (newer than last-seen, up to the running version), so
  a version skew between the changelog file and the running build can't leave an
  entry permanently un-dismissable.

## [1.4.0] — 2026-08-19

### License
- **RedWire is now licensed under Apache 2.0** (previously SSPL v1), and ships a
  NOTICE file. RedWire may now be used, modified, and redistributed — including
  in closed-source and commercial deployments — under Apache-2.0's permissive
  terms.

### Added
- **In-app help** — a `/help` guide hub with **User**, **Admin**, and **Plugins**
  guides (deep-linkable sections, live Mermaid diagrams, real in-app icons), plus
  a page-aware **?** button in the header that explains the current page and links
  into the relevant guide.
- **What's New** — the changelog is now reachable from the user menu.
- **Calendar timeline** — the planning timeline gains a **Calendar / Gantt toggle**
  and a custom **date-range filter**, with month navigation and per-day
  engagement chips.

### Improved
- **Custom-field editing** — text fields now edit with the rich Markdown editor
  and render as Markdown; findings and test-case edit pages moved custom fields
  into their own tab; custom-field sections (and evidence EXIF) collapse by
  default on detail views.
- **Faster large lists** — the Findings and Test Cases tabs use infinite scroll
  (the first page renders immediately, more stream in as you scroll) and no
  longer fire redundant per-row requests.
- **Faster engagement pages** — detail tabs load lazily via count/link endpoints,
  and profile-photo fetches are deduped and cached.
- **MCP server** migrated to the MCP 2.0 SDK.

### Fixed
- Findings tab now shows linked **test cases** in the links column.
- The Classification Marking card no longer renders empty on the edit-test-case
  page when no marking profile applies.

## [1.3.0] — 2026-08-13

A large feature release.

### Added
- **Custom fields** — admin-defined fields on assets, test cases, findings,
  clients, and engagements; usable as sortable table columns, searchable, in
  generated reports, and in the query builder.
- **Dashboards & widgets** — a much bigger query builder (20+ tables, richer
  operators, multi-source), a multi-query wizard for composite widget types,
  per-user activity series, and **tabbed global stats pages** with shared layouts.
- **Plugin system** — drop-in plugins with backend routers, frontend pages and
  in-page **extension slots** baked into the app, per-plugin migrations,
  lifecycle events, and RBAC.
- **Activity Feed** — the engagement *Logs* tab is now **Activity**, with a new
  **Feed**: a chronological, single-pane-of-glass stream of everything operators
  posted (comments, notes, findings, test cases, assets, evidence), with
  field-level **diffs** for finding/test-case edits. Search, type/action/author/
  date filters, sort, and paging.
- **Mermaid diagrams** — author ` ```mermaid ` blocks in any editor or markdown
  field; they render as live diagrams.
- **Notifications** — a full **/notifications** page (search, filters, sort,
  paging, per-item read/unread/delete), opt-in **per-user email notifications**
  as a styled HTML card, and a **password-changed security email**.
- **Scan history** — Nmap imports capture the exact command line and scan
  metadata (scanner, timing, host counts), kept as a revisitable per-engagement
  history.
- **Command palette + keyboard shortcuts** — Cmd/Ctrl+K, plus vim-style hotkey
  sequences.
- **Personal automations** — user-scoped automation rules alongside org rules.
- **Calendar views** — Day / Week / Month / **Gantt** toggle.
- **Attack-graph causal chains** — link test cases, findings, and vault items
  into cause→effect chains.
- **Version history + restore** for findings and test cases.
- **Tags on engagements**; **clipboard-paste uploads** + one shared dropzone
  across attachment surfaces; uploads persist across rebuilds.
- **AI & LDAP tooling** — custom headers / TLS-verify toggle / larger key field
  for AI providers; LDAP test-login + connection debug tracing.
- **In-app changelog** — a `/changelog` page and a one-time **"What's New"**
  popup after each update.
- **Per-feed TLS toggle** for internal / self-signed intel feeds.
- Engagement **Specs** (phases + dates), edit client info from the overview, a
  **"My Engagements"** filter, imports pre-scoped to an engagement, and `/health`
  build metadata surfaced in an admin **About** tab.

### Improved
- Global search now covers notes and comments.
- Query-builder filters use searchable entity pickers instead of raw IDs.
- @mentions show hover cards; mention notifications deep-link to the comment;
  comments are editable in threads.
- Scheduling: assign people to an engagement with a role; OoO exclusion uses a
  configurable time-overlap threshold.
- Clients: search + filter chips, sub-client actions, searchable parent picker.
- JSON report export includes entity relationships.
- Timestamps are localized consistently across the app.
- **Faster engagement pages** — detail tabs load their data only when opened
  rather than all up front; tab badges and the overview read lightweight count
  endpoints, and the findings / test-case tables batch their linked-note and
  linked intel/infrastructure lookups into a single request each instead of one
  per row.
- **Consistent page-title icons** — every top-level page now uses the same
  themed title-icon treatment.
- Profile photos load once and are cached instead of being re-fetched for every
  table row that shows the same author.

### Fixed
- Engagement tab counts show true totals (Assets no longer capped; Test Cases &
  Findings load the full list).
- Notes editor toolbar stays pinned while scrolling; list markers render;
  debounced note-edit logging restored.
- Faster engagements list for admins (fewer redundant permission fetches).
- Calendar weekend default + self Out-of-Office creation; widget tooltip
  clipping/theming; client tree badge rollup; several broken activity-log links.
- Pinned the MCP SDK so fresh builds don't pull a breaking 2.0 API.

## [1.2.0] — 2026-06-11

### Security
- Coordinated-disclosure hardening release: vault field encryption at rest and
  on import; auth/session hardening (HttpOnly refresh cookie, one-time TOTP,
  token-revocation fixes, rate-limited password reset with off-request email);
  plugin route authentication + runtime disable gate; automation template
  escaping and field constraints; input size caps (uploads, imports,
  comments/notes); server-side CSPRNG registration codes; profile-photo and
  `/uploads` lockdown; and more.

### Added
- **Report classification & portion marking** plus deep report customization.

## [1.1.0] — 2026-05-20

### Security
- Coordinated-disclosure security release (credited to the Lockheed Martin Red
  Team) — hardening across authentication, uploads, and API input validation.

## [1.0.0] — 2026-05-11

- Initial public release of the RedWire red-team operations platform:
  engagements, findings (CVSS-scored), assets, evidence, credential vault,
  cleanup artifacts, runbooks, reporting, scheduling, discussions, and team
  collaboration.
