// Test the specific failing case
fn main() {
    let width = 167u32;
    let height = 2390u32;
    let max_size = 521u32;
    
    let original_ratio = width as f64 / height as f64;
    println!("Original: {}x{}, ratio: {:.6}", width, height, original_ratio);
    
    // Simulate resize_image logic
    let max_dim = width.max(height);
    let scale = max_size as f32 / max_dim as f32;
    let new_width = (width as f32 * scale).round() as u32;
    let new_height = (height as f32 * scale).round() as u32;
    
    let new_ratio = new_width as f64 / new_height as f64;
    let ratio_diff = (original_ratio - new_ratio).abs() / original_ratio;
    
    println!("Resized: {}x{}, ratio: {:.6}", new_width, new_height, new_ratio);
    println!("Ratio diff: {:.4}%", ratio_diff * 100.0);
}
