# v1.4.7 Public Release Handoff

This is an internal operating checklist for the future public repositories. It
does not publish files or authorize a repository action.

## Required sequence

1. Review the proposed source-to-destination entries in
   `public_boundary/allowlist.json` and review the public Schema and license
   notices.
2. Run the generator into a new, empty directory outside this private
   repository:

   ```powershell
   .\.venv\Scripts\python.exe scripts/public_boundary.py build `
     --root . `
     --manifest public_boundary/allowlist.json `
     --output <clean-staging-directory>
   ```

3. Verify the generated file set, hashes, and scan result:

   ```powershell
   .\.venv\Scripts\python.exe scripts/public_boundary.py verify `
     --root <clean-staging-directory>
   ```

4. Record the source revision, Schema versions, hashes, dependency notices,
   license review, and human approver from `publication-manifest.json` in the
   release record. Do not copy the private repository's `.git` directory or
   use its commits as public history.
5. Create the destination public repository with a fresh Git history. Copy
   only the verified staging contents, inspect the resulting tree, and run the
   public repository's own tests and license checks.
6. Build and sign product packages in private infrastructure. Keep signing,
   cloud, Provider, billing, and infrastructure credentials outside the public
   repository and outside desktop/browser packages.
7. Publish only after boundary, licensing, security, artifact, and clean-client
   smoke approvals. A rejected scan or changed staging tree invalidates the
   release record and requires a new dry run.

## Explicit non-goals

- never change `video-summary-skill` visibility;
- never filter or rewrite private Git history into a public history;
- never treat an internal source ZIP as a public artifact;
- never include private core source, tests, prompts, models, output, logs,
  machine paths, Provider routes, or credentials in public staging;
- never place a formal cloud key in a browser extension or desktop client.

## v1.4.7 completion gate

The version is not boundary-complete until a clean staging run is reproducible,
`verify` passes after an independent review, the no-source packaging choice is
recorded, and the public repository/licensing review is complete. This branch
currently supplies the tooling and Schema fixture only; it does not create the
public repositories or perform that approval.
