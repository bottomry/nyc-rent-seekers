# Public-release gate

Every public release of NYC Rent Seekers must satisfy these checks against a
fresh clone:

1. Fixture-only CI and the production build are green.
2. `scrim private-paths . --history` reports no declared private path in the
   index or any reachable commit.
3. The complete public-push privacy gate has no blocking finding.
4. Generated browser artifacts contain no credential, private path, internal
   host, or maintainer-only documentation.
5. The static site works without private services or the private documentation
   companion. GitHub Pages is an acceptable free host when the repository is
   public and the Pages workflow passes.
6. A maintainer deliberately changes repository visibility only after the
   preceding evidence has been recorded.

Licensing is not an independent promotion gate. The technical, privacy, and CI
checks above are the release boundary.
