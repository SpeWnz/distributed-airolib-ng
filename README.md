# Distributed Airolib-ng
### Airolib-ng with a <i>distributed system</i> approach

<p>Version v241023</p>

## What is Airolib-ng ?

<p>Airolib-ng is a tool included in the <a href="https://github.com/aircrack-ng/aircrack-ng">Aicrack-ng</a> suite used specifically to precompute PMKs when performing Wireless Pentests.<p>

<p>The idea is to pre-calculate the passwords before performing the Wireless Pentest activity itself, in order to gain a significant advantage later, in terms of cracking time.</p>

## What is the problem with Airolib-ng?
<p>Airolib-ng itself doesn't have problems. However, it stores the precomputed PMKs and all its related data in a .DB file (an SQLite Database).</p>
<p>This is ideal for relatively small databases, but slowly becomes inefficient with larger and larger databases. Preformance start to degrade and datbase files become more and more sluggish.</p>

## What is the solution?
<p>For very large wordlists, one does not create a single database, but rather, many smaller pieces of database.</p>
<p>This way, smaller amounts of passwords can be computed at a time and performance does not degrade over time. </p>
<p>Better yet, if these database portions are distributed over multiple endpoints, crack times get decreased significantly.</p>
<p>Hence, the need of a distributed system approach.</p>

## How does this work?
<p>In short, the server listens for hosts who want to participate in the batch.</p>
<p>When a client connects, it will request a chunk to the server.</p>
<p>The client then batches the chunk, and when done, will submit said chunk back to the server.</p>
<p>Each chunk contains 1 million passwords <b>at most</b> (by default, but can be modified).</p>




## Usage:
### Requirements:
<p>This repo uses <a href="https://github.com/SpeWnz/ZHOR_Modules">ZHOR_Modules</a> as well as some other Python modules specified in the requirements.txt file. Make sure to install those first.</p>
<p>Endpoints running the client must have, of course, the Aircrack-ng suite installed (usually comes pre-installed with Kali distributions).</p>

### Workflow
<ol>

<li><p>Generate database chunks by issuing the following command:</p> 
<p><code>python3 make-db-chunks.py &ltwordlist&gt &ltssid list&gt</code></p>
<p>This will generate a folder containing all the chunks and a json file used by the server to keep track of the work. By default, the folder name will be the current date and timestamp.</p>
</li>

<li><p>If you want to host a server, check the parameters by issuing the following command:</p> 
<p><code>python3 server.py &ltport&gt &ltchunks folder&gt</code></p>
</li>

<li><p>If you want to run the client, check the parameters by issuing the following command:</p> 
<p><code>python3 client.py -h</code></p>
</li>

<li><p>With a browser, navigate to the server IP address to check the current status:</p>

<p>Main page: </p>
<img src="img/index.png">
<p>Performance dashboard:</p>
<img src="img/status.png">
</li>

</ol>

## Features
<ul>
<li>"Safe multithread": The script will prevent you from launching more airolib-ng instances than your core count.</li>
<li>Batch limit: it is possible to batch only a maximum amout of chunk if specified.</li>
<li>Continuous polling: clients will keep looking for new jobs from the server, never shutting down. Ideal in situations where clients are always online (for example, when clients are executed as a background service).</li>
<li>(TODO) Aircrack-ng adapter: a script that can ingest all of the db chunks and crack the password.</li>
<li>(TODO) Keyboard interrupt handling for the client.</li>

</ul>

## DISCLAIMER
<ul>
<li>The author of this repo does not hold responsible for any misuse or malicious use of the tools and scripts provided here.</li>
<li>This repo is supposed to be used inside a private or work LAN in which, presumably, all endpoints are trusted. While it is possible to use this repo with clients connecting outside of a LAN, it is not recommended for security purposes. If you want to, do so <b>at your own risk.</b></li>
<li>The author does not own Airolib-ng nor any tool of the Aircrack-ng suite. All rights belong to the respective owners.</li>
</ul>
