# Features

What the coding agent does, one file per capability. Each file says what the feature does,
how it behaves, where it lives in the code, and how it fails. The design reasoning behind
these lives in [`../concept.md`](../concept.md); these files describe the service as it is.

The service takes one GitHub issue, produces one pull request, and exits. In order of a run:

| Feature | Summary |
|---|---|
| [Task resolution](task-resolution.md) | Reads the Task File from GCS and builds the `TaskSpec` for the run. |
| [Skills at startup](skills-at-startup.md) | Installs the latest coding skills before anything else runs. |
| [Credentials from Secret Manager](credentials.md) | Loads the Claude and GitHub tokens at startup. |
| [Repository clone](repository-clone.md) | Clones the target repo into `/workspace`. |
| [Agent run](agent-run.md) | Runs the agent CLI with the fixed `/implement issue <url>` prompt. |
| [Run trace](run-trace.md) | Records every line the agent prints and writes it to GCS. |

Exit codes are defined in [`concept.md` §4.5](../concept.md#45-exit-code-taxonomy).
