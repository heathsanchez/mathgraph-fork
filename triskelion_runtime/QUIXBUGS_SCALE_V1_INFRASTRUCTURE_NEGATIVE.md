# Infrastructure negative retained

GitHub run `31846437763`, attempt 1, instantiated four arms successfully. The VERIFIED job spent approximately 17 minutes in `RiverProvider.__init__`, then raised `RuntimeError: River health check failed`. It made zero model calls and wrote no arm artifact. The aggregate failed only because that artifact was absent.

GitHub's "rerun failed jobs" operation was used without changing code, commit, corpus, prompts, seeds, settings, or completed-arm artifacts. Attempt 2 completed VERIFIED and the aggregate. This event is classified `INFRASTRUCTURE-BLOCKED`, not a scientific failure.
