use tokio::time::{sleep, Duration};
use battery::Manager;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manager = Manager::new()?;
    
    loop {
        if let Ok(batteries) = manager.batteries() {
            for battery in batteries {
                if let Ok(battery) = battery {
                    println!("Battery level: {:.2}%", 
                            battery.state_of_charge().value * 100.0);
                    println!("Status: {}", battery.state());
                }
            }
        }
        sleep(Duration::from_secs(60)).await;
    }
}
