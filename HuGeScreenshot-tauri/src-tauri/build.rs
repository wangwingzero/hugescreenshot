fn main() {
    // 读取 .env 并通过 cargo:rustc-env 嵌入到二进制（不以明文文件分发）
    embed_dotenv_at_compile_time();
    tauri_build::build();
    copy_openvino_dlls();
}

/// 读取 .env 文件中的后端敏感变量，通过 cargo:rustc-env 嵌入到二进制中。
/// 这样安装包不再包含明文 .env，密钥只存在于编译后的二进制中。
fn embed_dotenv_at_compile_time() {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let manifest_path = std::path::Path::new(&manifest_dir);

    // 查找 .env: 先看 src-tauri/（CI 复制过来的），再看仓库根目录
    let candidates = [
        manifest_path.join(".env"),
        manifest_path.parent().and_then(|p| p.parent()).map(|p| p.join(".env")).unwrap_or_default(),
    ];

    let env_file = candidates.iter().find(|p| p.exists());

    // 需要嵌入的后端变量列表
    let embed_keys = [
        "DEEPLX_URL",
        "DEEPLX_URL_FALLBACK",
    ];

    if let Some(env_path) = env_file {
        if let Ok(content) = std::fs::read_to_string(env_path) {
            for line in content.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some((key, value)) = line.split_once('=') {
                    let key = key.trim();
                    let value = value.trim();
                    if embed_keys.contains(&key) {
                        // 编译时嵌入：在源码中可用 env!() / option_env!() 读取
                        println!("cargo:rustc-env={}={}", key, value);
                    }
                }
            }
        }
        println!("cargo:rerun-if-changed={}", env_path.display());
    } else {
        // CI 环境中也可能通过系统环境变量传入
        for key in &embed_keys {
            if let Ok(val) = std::env::var(key) {
                println!("cargo:rustc-env={}={}", key, val);
            }
        }
    }

    // 监视文件变化
    println!("cargo:rerun-if-changed=.env");
    if let Some(root) = manifest_path.parent().and_then(|p| p.parent()) {
        println!("cargo:rerun-if-changed={}/.env", root.display());
    }
}

/// 自动复制 openvino DLL 到输出目录，确保运行时能找到 openvino_c.dll
fn copy_openvino_dlls() {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let src_dir = std::path::Path::new(&manifest_dir).join("openvino");

    if !src_dir.exists() {
        println!("cargo:warning=openvino 目录不存在: {}", src_dir.display());
        return;
    }

    let required_dlls = [
        "openvino_c.dll",
        "openvino.dll",
        "openvino_intel_cpu_plugin.dll",
        "openvino_ir_frontend.dll",
        "openvino_onnx_frontend.dll",
        "tbb12.dll",
        "tbbbind_2_5.dll",
        "tbbmalloc.dll",
        "tbbmalloc_proxy.dll",
    ];
    for dll in required_dlls {
        let path = src_dir.join(dll);
        if !path.exists() {
            println!(
                "cargo:warning=OpenVINO 必需 DLL 缺失: {}，打包后本地 OCR 可能无法启动",
                path.display()
            );
        }
    }

    // target/<profile>/ 目录
    let out_dir = std::env::var("OUT_DIR").unwrap();
    let target_dir =
        std::path::Path::new(&out_dir).ancestors().nth(3).expect("无法定位 target 输出目录");

    for entry in std::fs::read_dir(&src_dir).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if path.extension().is_some_and(|ext| ext == "dll") {
            let dest = target_dir.join(path.file_name().unwrap());
            let mut copied = false;
            for attempt in 0..3 {
                match std::fs::copy(&path, &dest) {
                    Ok(_) => {
                        copied = true;
                        break;
                    }
                    Err(e) => {
                        if attempt < 2 {
                            std::thread::sleep(std::time::Duration::from_millis(
                                500 * (attempt as u64 + 1),
                            ));
                        } else {
                            println!(
                                "cargo:warning=复制 {} 失败（重试 {} 次后）: {}",
                                path.display(),
                                attempt + 1,
                                e
                            );
                        }
                    }
                }
            }
            if !copied {
                println!(
                    "cargo:warning=⚠ OpenVINO DLL 未能复制: {}，运行时可能缺少依赖",
                    path.file_name().unwrap().to_string_lossy()
                );
            }
        }
    }

    // 当 openvino 目录内容变化时重新运行
    println!("cargo:rerun-if-changed=openvino/");
}
