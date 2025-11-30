// static/js/main.js
document.addEventListener("DOMContentLoaded", () => {
    console.log("UI loaded");

    // row highlight
    document.querySelectorAll("table tr").forEach(row => {
        row.addEventListener("click", () => {
            row.classList.toggle("selected-row");
        });
    });

    // wire global search inputs if present
    const searchInputs = document.querySelectorAll(".global-search-input");
    searchInputs.forEach(inp => {
        const btn = inp.parentElement.querySelector(".global-search-btn");
        const doSearch = () => {
            const q = inp.value.trim();
            if (!q) {
                showFloatingNotice("Type a plate or name to search");
                return;
            }
            fetch('/search?q=' + encodeURIComponent(q))
                .then(r => r.json())
                .then(data => {
                    renderSearchResults(data, inp);
                })
                .catch(e => {
                    showFloatingNotice("Search failed");
                    console.error(e);
                });
        };
        if (btn) btn.addEventListener('click', doSearch);
        inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
    });
});

// small floating notice
function showFloatingNotice(text, timeout=2000){
    let n = document.createElement('div');
    n.className = 'floating-notice';
    n.innerText = text;
    document.body.appendChild(n);
    setTimeout(()=> n.classList.add('visible'), 10);
    setTimeout(()=> { n.classList.remove('visible'); setTimeout(()=> n.remove(),300); }, timeout);
}

// render results into nearest .search-results container
function renderSearchResults(data, inputElement){
    // find nearest container
    let container = null;
    const page = document;
    container = page.querySelector('#search-results') || page.querySelector('.search-results');
    if(!container){
        container = document.createElement('div');
        container.className = 'search-results';
        document.body.insertBefore(container, document.body.firstChild);
    }
    container.style.display = 'block';
    let html = '';
    if(data.vehicles && data.vehicles.length){
        html += '<h3>Registered Vehicles</h3>';
        html += '<table class="table"><thead><tr><th>Plate</th><th>Name</th><th>Type</th><th>Mobile</th></tr></thead><tbody>';
        data.vehicles.forEach(v=>{
            html += `<tr><td>${v.plate_number}</td><td>${v.full_name}</td><td>${v.vehicle_type||''}</td><td>${v.mobile_no||''}</td></tr>`;
        });
        html += '</tbody></table>';
    }
    if(data.logs && data.logs.length){
        html += '<h3>Parking Logs</h3>';
        html += '<table class="table"><thead><tr><th>ID</th><th>Plate</th><th>Time In</th><th>Time Out</th><th>Area</th></tr></thead><tbody>';
        data.logs.forEach(l=>{
            html += `<tr><td>${l.id}</td><td>${l.plate_number}</td><td>${l.time_in||'-'}</td><td>${l.time_out||'-'}</td><td>${l.parking_area||'-'}</td></tr>`;
        });
        html += '</tbody></table>';
    }
    if((!data.logs || data.logs.length===0) && (!data.vehicles || data.vehicles.length===0)){
        html = '<p>No results found.</p>';
    }
    container.innerHTML = html;
}
