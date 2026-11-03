# Authorization matrix

WizDesk calls its workspace a **team**. Tasks belong directly to a team; there is no project model or project membership policy. This matrix describes the implemented API policy, not a proposed project feature. `users/tests/test_authorization_matrix.py` exercises the actor cases and ID based endpoints.

| Actor | View team task and subtask | Create/edit/delete task | Claim subtask | Edit/delete subtask | Approve/remove member | Django admin |
| --- | --- | --- | --- | --- | --- | --- |
| Current team leader | Yes | Yes | No | Yes | Yes | Only if `is_staff` |
| Approved team member | Yes | No | Yes, if unassigned | Progress on own assignment only | No | No |
| Pending or rejected member | No | No | No | No | No | No |
| Leader of another team | No | No | No | No | No | Only if `is_staff` |
| Anonymous | No | No | No | No | No | No |
| User with `ADMIN` role | Yes in their current team | No | No | No | No | Only if `is_staff` |

The API reads current membership from the database for each JWT request and refresh. A changed role or team takes effect on the next request; rejected or detached users cannot use an already issued access token. Leader mutations lock and recheck the actor inside the transaction. Task and subtask detail lookups include the current team, and list endpoints cannot return another team's rows. The assigned-subtask endpoint also rejects another team's user ID.

Joining with a team code creates a pending member. The current leader must approve the member before task access. The code is a join credential, not a single-use invitation. There is no invitation object, expiry, or revocation flow yet.

`ADMIN` is a stored role value without a separate API management policy. It does not imply Django `is_staff` or `is_superuser` and does not grant leader mutations. Django admin permissions remain controlled by Django staff and model permissions.
