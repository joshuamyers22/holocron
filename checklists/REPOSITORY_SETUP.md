# Repository Setup

Complete this checklist for every new project or repository before the first
commit or push. Git author identity, GitHub authentication, and repository
ownership are separate controls; verify all three.

## Git author identity

- [x] Initialize Git when needed with `git init`.
- [x] Configure the author in this repository rather than relying only on global
      defaults:

  ```sh
  git config --local user.name "YOUR NAME"
  git config --local user.email "YOUR VERIFIED OR GITHUB NOREPLY EMAIL"
  ```

- [x] Verify both local values and their source:

  ```sh
  git config --local --get user.name
  git config --local --get user.email
  git config --show-origin --get user.name
  git config --show-origin --get user.email
  ```

  The `--show-origin` results must resolve to this repository's `.git/config`.
  Use an email associated with the intended GitHub account so GitHub can
  attribute commits correctly.

## GitHub account and repository

- [x] Confirm the intended account is authenticated. The repository was created
      with the authenticated `joshuamyers22` account. If more than one account is
      available, select the correct one before creating or connecting the
      repository:

  ```sh
  gh auth status
  gh auth switch --user GITHUB_ACCOUNT
  gh auth setup-git
  ```

- [x] Create the GitHub repository under that account or an explicitly approved
      organization, or connect the existing repository as `origin`. Choose
      visibility deliberately; private is the safe default for new work:

  ```sh
  gh repo create OWNER/REPOSITORY --source=. --remote=origin --private
  ```

  For an existing GitHub repository, add its SSH or HTTPS URL with
  `git remote add origin URL`. Do not replace an existing remote until its owner
  and purpose have been verified.

- [x] Verify that the authenticated account can access the same canonical
      repository named by `origin`:

  ```sh
  git remote get-url origin
  gh repo view OWNER/REPOSITORY --json nameWithOwner,url,viewerPermission
  ```

- [x] Use the same canonical `OWNER/REPOSITORY` in the project manifest and all
      repository, issue-tracker, changelog, and documentation URLs.
- [x] Confirm `.github/CODEOWNERS` names the intended account or team.
- [x] Keep tokens, keys, cookies, and credential-helper output out of the
      repository and its documentation.
