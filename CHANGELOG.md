# CHANGELOG


## v1.0.1-dev.3 (2026-06-16)

### 🐛 Bug Fixes

- Serve static assets via constant path lookup
  ([`b073e21`](https://github.com/orel-mor/Whitelistarr/commit/b073e216f95dff7d358058c4bc19d0196babba10))


## v1.0.1-dev.2 (2026-06-16)

### 🐛 Bug Fixes

- Satisfy CodeQL on the static route and secret logging
  ([`69a7ceb`](https://github.com/orel-mor/Whitelistarr/commit/69a7ceb09ca0ff71a1c9ba87fc293681c5a7ce04))


## v1.0.1-dev.1 (2026-06-16)


## v1.0.0 (2026-06-16)

### ♻️ Refactoring

- Rename secret loop variable to clear false-positive alert
  ([`d5346fe`](https://github.com/orel-mor/Whitelistarr/commit/d5346fe33c921643f44b9db851c26b97b50af581))


## v1.0.0-dev.2 (2026-06-16)

### 🐛 Bug Fixes

- Confine web UI static file route to its directory
  ([`ae75a47`](https://github.com/orel-mor/Whitelistarr/commit/ae75a472ddb84ced292d6995f2de3f40b592a076))

- Pin tzlocal to avoid the broken 5.4.2 wheel
  ([`639796e`](https://github.com/orel-mor/Whitelistarr/commit/639796e91ce9ac0e39835f943677d41a539fca67))

### Chores

- Remove build.sh and committed editor settings
  ([`181a1eb`](https://github.com/orel-mor/Whitelistarr/commit/181a1eb49e5b04ab3acf08b3b6d8f7e7d4e8097d))

### ⚙️ CI

- Bump docker/build-push-action from 6 to 7 ([#5](https://github.com/orel-mor/Whitelistarr/pull/5),
  [`aa27b33`](https://github.com/orel-mor/Whitelistarr/commit/aa27b33cccb3d1bde00592f6b614c865c7c0317b))

- Bump docker/login-action from 3 to 4 ([#1](https://github.com/orel-mor/Whitelistarr/pull/1),
  [`7fadd5a`](https://github.com/orel-mor/Whitelistarr/commit/7fadd5a16149394df77cf909b6681cae26bf64f4))

- Bump docker/setup-buildx-action from 3 to 4
  ([#3](https://github.com/orel-mor/Whitelistarr/pull/3),
  [`84e2340`](https://github.com/orel-mor/Whitelistarr/commit/84e2340c450ea30ad0ce78f8c48f37569dc8803d))

- Bump docker/setup-qemu-action from 3 to 4 ([#4](https://github.com/orel-mor/Whitelistarr/pull/4),
  [`e7ee8f8`](https://github.com/orel-mor/Whitelistarr/commit/e7ee8f803cea7497d78805bf37566abe1de5fc0a))

- Bump github/codeql-action from 3 to 4 ([#2](https://github.com/orel-mor/Whitelistarr/pull/2),
  [`9727950`](https://github.com/orel-mor/Whitelistarr/commit/9727950e1b0996ac3d006c4fd83ad46ab04ef699))

### 📝 Documentation

- Rewrite README, add CONTRIBUTING, de-personalize examples
  ([`c47d686`](https://github.com/orel-mor/Whitelistarr/commit/c47d686cf42602518fade70dce0d5bd45bbb0704))

### 🧪 Tests

- Use neutral fixture names
  ([`5aab32b`](https://github.com/orel-mor/Whitelistarr/commit/5aab32bd542b42c374c65533666ef439e30af0ba))


## v1.0.0-dev.1 (2026-06-16)

- Initial Release
