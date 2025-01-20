const batteryChart = new Chart(document.getElementById('batteryChart'), {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Battery Level',
            data: []
        }]
    }
});

function updateBatteryStatus(data) {
    document.getElementById('batteryLevel').textContent = `${data.percent}%`;
    document.getElementById('chargingStatus').textContent = 
        data.power_plugged ? 'Plugged In' : 'On Battery';
    
    // Update chart
    batteryChart.data.labels.push(new Date().toLocaleTimeString());
    batteryChart.data.datasets[0].data.push(data.percent);
    batteryChart.update();
}
