//! Managed Python runtime for packaged desktop installs.
//!
//! Release bundles ship a `runtime/` resource directory with the Locus wheel,
//! a prebuilt `locus_rust` wheel, a hash-locked `requirements.txt` exported
//! from `uv.lock`, and a `manifest.json` that names them. On first launch the
//! bundled `uv` creates a private virtual environment, with a uv-managed
//! CPython, under `~/.locus/desktop-runtime` and installs from those files.
//! End users need no git, Python, or Rust toolchain.

use std::path::{Path, PathBuf};

/// Resource sub-directory that holds the bundled runtime files.
pub const RUNTIME_RESOURCE_DIR: &str = "runtime";
const MANIFEST_FILE: &str = "manifest.json";
/// Written after a successful install; holds the manifest it was built from.
const STAMP_FILE: &str = "installed.json";
const STDERR_TAIL_CHARS: usize = 1500;

/// A runtime bundled with this build of the desktop app.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BundledRuntime {
    /// Raw manifest text, also written as the install stamp so a new app
    /// version (new manifest) triggers a reinstall.
    pub manifest: String,
    /// uv Python request, e.g. `3.12` or `cpython-3.12-windows-x86_64-none`.
    pub python: String,
    pub requirements: PathBuf,
    /// Installed after the locked requirements, without dependency resolution.
    pub wheels: Vec<PathBuf>,
}

#[derive(serde::Deserialize)]
struct Manifest {
    python: String,
    requirements: String,
    wheels: Vec<String>,
}

/// Parse `manifest` and check that every file it names exists in `dir`.
pub fn parse_bundled_runtime(dir: &Path, manifest: &str) -> Result<BundledRuntime, String> {
    let parsed: Manifest = serde_json::from_str(manifest)
        .map_err(|e| format!("The bundled runtime manifest is invalid: {}", e))?;
    if parsed.python.trim().is_empty() || parsed.wheels.is_empty() {
        return Err("The bundled runtime manifest lists no Python version or wheels.".into());
    }
    let requirements = dir.join(&parsed.requirements);
    let wheels: Vec<PathBuf> = parsed.wheels.iter().map(|w| dir.join(w)).collect();
    for path in std::iter::once(&requirements).chain(wheels.iter()) {
        if !path.is_file() {
            return Err(format!(
                "A bundled runtime file is missing: {}. Reinstall Locus.",
                path.display()
            ));
        }
    }
    Ok(BundledRuntime {
        manifest: manifest.to_string(),
        python: parsed.python,
        requirements,
        wheels,
    })
}

/// The runtime bundled under `resource_dir`. `None` means this build ships
/// no runtime (development builds); `Some(Err)` means the bundle is broken.
pub fn bundled_runtime(resource_dir: &Path) -> Option<Result<BundledRuntime, String>> {
    let dir = resource_dir.join(RUNTIME_RESOURCE_DIR);
    let manifest = std::fs::read_to_string(dir.join(MANIFEST_FILE)).ok()?;
    Some(parse_bundled_runtime(&dir, &manifest))
}

pub fn runtime_home(home: &str) -> PathBuf {
    PathBuf::from(home).join(".locus").join("desktop-runtime")
}

pub fn venv_dir(runtime_home: &Path) -> PathBuf {
    runtime_home.join("venv")
}

pub fn venv_python(venv: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

pub fn venv_locus(venv: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        venv.join("Scripts").join("locus.exe")
    } else {
        venv.join("bin").join("locus")
    }
}

/// True when `runtime_home` holds a complete install of exactly `runtime`.
pub fn is_installed(runtime_home: &Path, runtime: &BundledRuntime) -> bool {
    venv_locus(&venv_dir(runtime_home)).is_file()
        && std::fs::read_to_string(runtime_home.join(STAMP_FILE))
            .map(|stamp| stamp == runtime.manifest)
            .unwrap_or(false)
}

/// One `uv` invocation of the first-launch install, with its progress label.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstallStep {
    /// Progress text shown while the step runs.
    pub detail: &'static str,
    /// Short name used in failure messages.
    pub name: &'static str,
    pub args: Vec<String>,
}

/// The `uv` commands that install `runtime` into `runtime_home`. Pure, so the
/// exact arguments are unit-tested.
pub fn install_steps(runtime: &BundledRuntime, runtime_home: &Path) -> Vec<InstallStep> {
    let venv = venv_dir(runtime_home);
    let python = venv_python(&venv).display().to_string();
    let mut wheel_args: Vec<String> = ["pip", "install", "--python", &python, "--no-deps"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    wheel_args.extend(runtime.wheels.iter().map(|w| w.display().to_string()));
    vec![
        InstallStep {
            detail: "Setting up Python (first launch)...",
            name: "setting up Python",
            args: vec![
                "venv".into(),
                "--python".into(),
                runtime.python.clone(),
                "--managed-python".into(),
                venv.display().to_string(),
            ],
        },
        InstallStep {
            detail: "Installing Python packages (first launch, this can take a few minutes)...",
            name: "installing Python packages",
            args: vec![
                "pip".into(),
                "install".into(),
                "--python".into(),
                python,
                "--no-deps".into(),
                "--require-hashes".into(),
                "-r".into(),
                runtime.requirements.display().to_string(),
            ],
        },
        InstallStep {
            detail: "Installing Locus...",
            name: "installing Locus",
            args: wheel_args,
        },
    ]
}

/// Environment for every `uv` call: keep Python, caches and settings inside
/// the runtime home so a user's own uv setup can't change the install.
pub fn uv_env(runtime_home: &Path) -> Vec<(&'static str, String)> {
    vec![
        (
            "UV_PYTHON_INSTALL_DIR",
            runtime_home.join("python").display().to_string(),
        ),
        (
            "UV_CACHE_DIR",
            runtime_home.join("cache").display().to_string(),
        ),
        ("UV_NO_CONFIG", "1".into()),
        ("UV_PYTHON_DOWNLOADS", "automatic".into()),
    ]
}

/// Remove a partial or outdated install so the next steps start clean. The
/// downloaded Python and cache are kept to make a retry faster.
pub fn reset_install(runtime_home: &Path) -> Result<(), String> {
    let _ = std::fs::remove_file(runtime_home.join(STAMP_FILE));
    let venv = venv_dir(runtime_home);
    if venv.exists() {
        std::fs::remove_dir_all(&venv).map_err(|e| {
            format!(
                "Could not remove the old runtime at {}: {}",
                venv.display(),
                e
            )
        })?;
    }
    std::fs::create_dir_all(runtime_home)
        .map_err(|e| format!("Could not create {}: {}", runtime_home.display(), e))
}

/// Record a finished install and drop the download cache it no longer needs.
pub fn mark_installed(runtime_home: &Path, runtime: &BundledRuntime) -> Result<(), String> {
    std::fs::write(runtime_home.join(STAMP_FILE), &runtime.manifest)
        .map_err(|e| format!("Could not record the runtime install: {}", e))?;
    let _ = std::fs::remove_dir_all(runtime_home.join("cache"));
    Ok(())
}

/// Hide the console window that Windows opens for console-subsystem children.
pub fn hide_console_window(cmd: &mut tokio::process::Command) {
    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(target_os = "windows"))]
    let _ = cmd;
}

fn stderr_tail(stderr: &[u8]) -> String {
    let text = String::from_utf8_lossy(stderr);
    let total = text.chars().count();
    text.chars()
        .skip(total.saturating_sub(STDERR_TAIL_CHARS))
        .collect::<String>()
        .trim()
        .to_string()
}

/// User-facing message for a failed first-launch step.
pub fn format_install_failure(runtime_home: &Path, step_name: &str, output: &str) -> String {
    format!(
        "First-launch setup failed while {}.\n\nLast output:\n{}\n\n\
         Check your internet connection, then relaunch Locus to retry. \
         To start the setup over, delete {} and relaunch.",
        step_name,
        if output.is_empty() {
            "(no output)"
        } else {
            output
        },
        runtime_home.display(),
    )
}

/// Run one program with the runtime environment and fail with its stderr.
pub async fn run_step(
    program: &Path,
    args: &[String],
    runtime_home: &Path,
    prepare: fn(&mut tokio::process::Command),
) -> Result<(), String> {
    let mut cmd = tokio::process::Command::new(program);
    cmd.args(args)
        .envs(uv_env(runtime_home))
        .current_dir(runtime_home)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    prepare(&mut cmd);
    hide_console_window(&mut cmd);
    match cmd.output().await {
        Ok(out) if out.status.success() => Ok(()),
        Ok(out) => Err(stderr_tail(&out.stderr)),
        Err(e) => Err(format!("could not run {}: {}", program.display(), e)),
    }
}

/// Check that the installed environment can import Locus and its extension.
pub fn verify_args() -> Vec<String> {
    vec!["-c".into(), "import locus, locus_rust".into()]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "locus-runtime-test-{}-{}",
            name,
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    const MANIFEST: &str = r#"{
        "python": "3.12",
        "requirements": "requirements.txt",
        "wheels": ["locus_rust-1.0.0-cp312-cp312-win_amd64.whl", "locus_assistant-1.0.0-py3-none-any.whl"]
    }"#;

    fn bundle(name: &str) -> PathBuf {
        let dir = temp_dir(name);
        for file in [
            "requirements.txt",
            "locus_rust-1.0.0-cp312-cp312-win_amd64.whl",
            "locus_assistant-1.0.0-py3-none-any.whl",
        ] {
            std::fs::write(dir.join(file), "").unwrap();
        }
        dir
    }

    #[test]
    fn parses_manifest_and_resolves_files() {
        let dir = bundle("parse");
        let rt = parse_bundled_runtime(&dir, MANIFEST).unwrap();
        assert_eq!(rt.python, "3.12");
        assert_eq!(rt.requirements, dir.join("requirements.txt"));
        assert_eq!(
            rt.wheels,
            vec![
                dir.join("locus_rust-1.0.0-cp312-cp312-win_amd64.whl"),
                dir.join("locus_assistant-1.0.0-py3-none-any.whl"),
            ]
        );
    }

    #[test]
    fn rejects_manifest_naming_missing_files() {
        let dir = temp_dir("missing");
        std::fs::write(dir.join("requirements.txt"), "").unwrap();
        let err = parse_bundled_runtime(&dir, MANIFEST).unwrap_err();
        assert!(err.contains("missing"), "{err}");
    }

    #[test]
    fn rejects_manifest_without_wheels() {
        let dir = bundle("empty");
        let err = parse_bundled_runtime(
            &dir,
            r#"{"python": "3.12", "requirements": "requirements.txt", "wheels": []}"#,
        )
        .unwrap_err();
        assert!(err.contains("no Python version or wheels"), "{err}");
    }

    #[test]
    fn no_bundle_means_development_build() {
        let dir = temp_dir("none");
        assert!(bundled_runtime(&dir).is_none());
    }

    #[test]
    fn install_steps_create_venv_then_install_locked_then_wheels() {
        let dir = bundle("steps");
        let rt = parse_bundled_runtime(&dir, MANIFEST).unwrap();
        let home = dir.join("home");
        let steps = install_steps(&rt, &home);
        let venv = venv_dir(&home).display().to_string();
        let python = venv_python(&venv_dir(&home)).display().to_string();

        assert_eq!(steps.len(), 3);
        assert_eq!(
            steps[0].args,
            vec![
                "venv",
                "--python",
                "3.12",
                "--managed-python",
                venv.as_str()
            ]
        );
        assert_eq!(
            steps[1].args,
            vec![
                "pip",
                "install",
                "--python",
                python.as_str(),
                "--no-deps",
                "--require-hashes",
                "-r",
                dir.join("requirements.txt").display().to_string().as_str(),
            ]
        );
        assert_eq!(
            &steps[2].args[..5],
            &["pip", "install", "--python", python.as_str(), "--no-deps"]
        );
        assert_eq!(steps[2].args.len(), 7);
    }

    #[test]
    fn stamp_must_match_manifest_and_locus_must_exist() {
        let dir = bundle("stamp");
        let rt = parse_bundled_runtime(&dir, MANIFEST).unwrap();
        let home = dir.join("home");
        reset_install(&home).unwrap();
        assert!(!is_installed(&home, &rt));

        let locus = venv_locus(&venv_dir(&home));
        std::fs::create_dir_all(locus.parent().unwrap()).unwrap();
        std::fs::write(&locus, "").unwrap();
        assert!(!is_installed(&home, &rt), "no stamp yet");

        mark_installed(&home, &rt).unwrap();
        assert!(is_installed(&home, &rt));

        let newer = BundledRuntime {
            manifest: MANIFEST.replace("1.0.0", "1.0.1"),
            ..rt.clone()
        };
        assert!(!is_installed(&home, &newer), "a new app version reinstalls");

        reset_install(&home).unwrap();
        assert!(!locus.exists());
        assert!(!is_installed(&home, &rt));
    }

    #[test]
    fn uv_env_keeps_python_and_cache_in_runtime_home() {
        let home = PathBuf::from("rt-home");
        let env = uv_env(&home);
        assert!(env.contains(&("UV_NO_CONFIG", "1".to_string())));
        assert!(env.contains(&(
            "UV_PYTHON_INSTALL_DIR",
            home.join("python").display().to_string()
        )));
        assert!(env.contains(&("UV_CACHE_DIR", home.join("cache").display().to_string())));
    }

    #[test]
    fn failure_message_names_step_and_reset_path() {
        let msg = format_install_failure(Path::new("rt-home"), "installing Locus", "boom");
        assert!(msg.contains("failed while installing Locus."), "{msg}");
        assert!(msg.contains("boom"));
        assert!(msg.contains("rt-home"));
        let empty = format_install_failure(Path::new("rt-home"), "installing Locus", "");
        assert!(empty.contains("(no output)"));
    }
}
