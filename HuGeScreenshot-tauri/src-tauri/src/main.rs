// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    hugescreenshot_tauri_lib::configure_webview2_compatibility();

    #[cfg(windows)]
    let _single_instance_lock =
        if hugescreenshot_tauri_lib::single_instance::is_webview_child_process() {
            None
        } else {
            match hugescreenshot_tauri_lib::single_instance::SingleInstanceLock::acquire() {
            Ok(lock) => Some(lock),
            Err(error)
                if hugescreenshot_tauri_lib::single_instance::should_exit_for_single_instance_error(
                    &error,
                ) =>
            {
                return;
            }
            Err(error) => {
                eprintln!("单实例锁初始化失败，继续启动应用: {}", error);
                None
            }
        }
        };

    hugescreenshot_tauri_lib::run()
}
