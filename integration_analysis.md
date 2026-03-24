# Frontend-Backend Integration Analysis

## The Disconnect
The frontend relies heavily on inline HTML/JS scripts doing explicit `fetch` calls to legacy Node.js/Express routes. The new Django backend (implemented via DRF ViewSets) exposed standard RESTful routes, which don't match the frontend. 

Rather than changing the hundreds of `fetch` calls and response parsing logic across multiple HTML files, we will **refactor the Django views and urls to match the frontend expectations**.

## Required Auth Endpoints
| Frontend Expected Route | Method | Payload | Expected Response |
|--|--|--|--|
| `/api/auth/send-verification` | POST | `name, email, password, teamName` | `{ verificationToken, emailSent, emailMethod }` |
| `/api/auth/verify-email` | POST | `token` | Creates Leader user |
| `/api/auth/send-member-verification` | POST | `name, email, password, teamCode` | `{ verificationToken, teamName, emailSent, emailMethod }` |
| `/api/auth/verify-member-email` | POST | `token` | Creates Member user (Pending) |
| `/api/auth/login/` | POST | `email, password` | `{ token, user: {...} }` *(Currently working!)* |
| `/api/auth/check-member-status` | POST | `{ email }` | `{ status }` |
| `/api/auth/team/{code}/all-members` | GET | `None` | `[ { id, name, email, role, status, ... }, ... ]` |
| `/api/auth/team/{code}/pending-requests`| GET | `None` | `[ { id, name, email, ... } ]` |
| `/api/auth/team/{code}/rejected-members`| GET | `None` | `[ { id, name, email, ... } ]` |
| `/api/auth/approve-member` | POST | `{ leaderId, userId }` | `{ message }` |
| `/api/auth/reject-member` | POST | `{ leaderId, userId }` | `{ message }` |
| `/api/auth/approve-rejected-member`| POST | `{ leaderId, userId }` | `{ message }` |
| `/api/auth/delete-rejected-member/{id}`| DELETE| `None` | `{ message }` |
| `/api/auth/team/{code}/member/{id}`| DELETE| `{ leaderId }` | `{ message }` |
| `/api/auth/team/{code}/members` | GET | `None` | `[ { id, name,... } ]` *(Only approved team members)* |

## Required Tasks & Subtasks Endpoints
| Frontend Expected Route | Method | Payload | Expected Response |
|--|--|--|--|
| `/api/tasks/` | POST | `{ title, description, teamCode, createdBy, subtasks, assignSpecific }` | `{ task: {...} }` *(We modified frontend to use POST /tasks/ instead of /tasks/create)* |
| `/api/tasks/team/{code}` | GET | `None` | `[ { id, title, subtasks: [...], assignees: [...] } ]` |
| `/api/tasks/team/{code}/status/{status}`| GET | `None` | `[ ... filtered tasks ]` |
| `/api/tasks/{taskId}` | GET | `None` | `{ id, title, subtasks: [...] }` |
| `/api/tasks/{taskId}` | PUT | `{ status }` | `{ message, task }` |
| `/api/tasks/{taskId}` | DELETE| `{ leaderId }` | `{ message }` |
| `/api/tasks/subtask/{subtask.id}` | DELETE| `None` | `{ message }` |
| `/api/tasks/user/{userId}/subtasks` | GET | `None` | `[ { id, title, task_title, status, progress, deadline } ]` |
| `/api/tasks/subtask/{subtaskId}/take`| POST | `None` | `{ message }` |
| `/api/tasks/subtask/{subtaskId}/progress`|POST | `{ progress }` | `{ message }` |
| `/api/tasks/subtask/{subtaskId}` | GET | `None` | `{ id, title, ... }` |

## Required Performance Endpoints
| Frontend Expected Route | Method | Payload | Expected Response |
|--|--|--|--|
| `/api/performance/team/{code}` | GET | `None` | `{ totalTasks, completedTasks, activeTasks, productivityScore, totalMembers, memberStats: [ {id, name, completed_tasks, active_tasks} ] }` |

## Action Plan
1. **Refactor Auth**: Update `users/urls.py` and views to mock verification (auto-approve email or generate a fake token) and handle all custom `/auth/team/...` routes.
2. **Refactor Tasks**: Instead of standard `/tasks/` and `/subtasks/` viewsets, we need to map the exact Express routes (`/tasks/team/<code/>`, etc.) in `tasks/urls.py` mapped to APIViews.
3. **Refactor Performance**: Implement `/performance/team/{code}` to aggregate team stats.
