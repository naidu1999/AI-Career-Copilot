# Connector matrix

| Provider | Method | Key | Default |
|---|---|---:|---:|
| Greenhouse | Public Job Board JSON API | No | Company entries disabled |
| Lever | Public postings JSON API | No | Company entries disabled |
| Ashby | Public posting JSON API | No | User-added |
| SmartRecruiters | Public postings JSON API | No | User-added |
| Recruitee | Public offers JSON API | No | User-added |
| Arbeitnow | Public job-board API | No | Enabled |
| Adzuna India | Official search API | Yes | Enabled only when configured |
| Jooble | Official REST API | Yes | Enabled only when configured |
| USAJOBS | Official federal API | Yes | Disabled |
| Manual | User-supplied official URL | No | Available |

No connector authenticates to a job portal, reads restricted HTML, solves CAPTCHAs,
or submits an application. Company slugs can change or be disabled, so every catalogue
entry must succeed at runtime before the user enables it.
