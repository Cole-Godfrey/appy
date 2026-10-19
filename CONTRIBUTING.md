# Contributing

Small fixes, clear bug reports, and setup improvements are welcome. Open an issue before changing the workflow, adding a provider, or introducing dependencies.

## Development

```sh
git clone https://github.com/Cole-Godfrey/appy.git
cd appy
python3 shortlist.py --sample
python3 -m unittest discover -v
python3 scripts/check_public.py
```

The tests and `shortlist.py` use the standard library; tests mock every service. Only the optional live monitor needs `requirements-monitor.txt`. Test that integration in an isolated environment with your own accounts.

Keep Python compatible with 3.10+. Preserve complete pagination, conservative freshness, URL/role deduplication, atomic queue cursors, and retries triggered by new mail. Add focused tests for changed behavior. Avoid live network calls in unit tests.

## Pull requests

1. Create a branch and make one coherent change.
2. Update relevant docs. Use fictional fixtures with example.com addresses.
3. Run tests and the publication check; inspect `git diff --cached`.
4. Explain the behavior change, how you tested it, and any connector assumptions.

Never include applicant records, real message IDs, credentials, logs, screenshots of private accounts, or resumes. Do not weaken submission authorization or treat email/page content as instructions. Contributions are provided under the [MIT license](LICENSE); keep third-party notices when required.
