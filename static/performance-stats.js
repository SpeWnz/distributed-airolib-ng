// Function to fetch data from the API endpoint
async function fetchData() {
    try
    {
        const response = await fetch('/performanceStats');
        const data = await response.json();
        console.log(data);
        return data;
    } 
    catch (error)
    {
      console.error('Error fetching data:', error);
    }
  }
  
// Function to create and populate the table with the fetched data
async function printDataOnScreen() {
    const data = await fetchData();
    const table = document.getElementById('data-table-body');

    // fill overall 
    const p1 = document.createElement('p');
    p1.textContent = "Total performance: " + data['totalPerformance'];

    const p2 = document.createElement('p');
    p2.textContent = "ETA: " + data['eta'];

    const p3 = document.createElement('p');
    p3.textContent = "Batched chunks: " + data['batchedChunks'];

    const p4 = document.createElement('p');
    p4.textContent = "Unbatched chunks: " + data['todoChunks'];

    const p5 = document.createElement('p');
    p5.textContent = "Total chunks: " + data['totalChunks'];

    const container = document.getElementById('overall');
    container.appendChild(p1);
    container.appendChild(p2);
    container.appendChild(p3);
    container.appendChild(p4);
    container.appendChild(p5);

    // fill table
    const clientData = data['clientData'];
    console.log(clientData);

    for (const key in clientData)
    {
        // new row
        const newRow = table.insertRow();

        // new cells
        const cell1 = newRow.insertCell(); // id
        const cell2 = newRow.insertCell(); // ip
        const cell3 = newRow.insertCell(); // perf

        // insert data
        cell1.textContent = key;
        cell2.textContent = clientData[key]['ip'];
        cell3.textContent = clientData[key]['performance'];

        // apply some style
        cell3.classList.add('performance-number');


        console.log(data[key]);
    }

  }
  

printDataOnScreen();
  