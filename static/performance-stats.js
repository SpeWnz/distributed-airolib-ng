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
    
  function createUnorderedList(list) 
  {
    // Create an unordered list element
    const ulElement = document.createElement('ul');

    // Iterate through the list and create list items for each element
    list.forEach(item => {
      // Create a list item element
      const liElement = document.createElement('li');
      
      // Set the text content of the list item to the current item in the list
      liElement.textContent = item;
      
      // Append the list item to the unordered list
      ulElement.appendChild(liElement);
    });

    // Return the unordered list element
    return ulElement;
  }
  
  
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
    p5.textContent = "WIP chunks: " + data['wipChunks'];

    const p6 = document.createElement('p');
    p6.textContent = "Total chunks: " + data['totalChunks'];

    const container = document.getElementById('overall');
    container.appendChild(p1);
    container.appendChild(p2);
    container.appendChild(p3);
    container.appendChild(p4);
    container.appendChild(p5);
    container.appendChild(p6);

    // fill table
    const clientData = data['clientStatusDictionary'];
    console.log(clientData);

    for (const key in clientData)
    {
        // new row
        const newRow = table.insertRow();

        // new cells
        const cell1 = newRow.insertCell(); // id
        const cell2 = newRow.insertCell(); // ip
        const cell3 = newRow.insertCell(); // perf
        const cell4 = newRow.insertCell(); // working chunks

        // insert data
        cell1.textContent = clientData[key]['clientID'];
        cell2.textContent = clientData[key]['ip'];
        cell3.textContent = clientData[key]['performance'];
        cell4.appendChild(createUnorderedList(clientData[key]['chunks']))

        // apply some style
        cell3.classList.add('performance-number');


        console.log(data[key]);
    }

  }
  

printDataOnScreen();