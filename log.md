PS D:\\Code> python .\\export\_punch\_records.py

Traceback (most recent call last):

&#x20; File "D:\\Code\\export\_punch\_records.py", line 288, in <module>

&#x20;   main()

&#x20;   \~\~\~\~^^

&#x20; File "D:\\Code\\export\_punch\_records.py", line 283, in main

&#x20;   output\_path, row\_count = export\_to\_csv(start\_time, end\_time, Path(args.output))

&#x20;                            \~\~\~\~\~\~\~\~\~\~\~\~\~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20; File "D:\\Code\\export\_punch\_records.py", line 255, in export\_to\_csv

&#x20;   for device in load\_device\_configs():

&#x20;                 \~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "D:\\Code\\export\_punch\_records.py", line 83, in load\_device\_configs

&#x20;   raise EnvironmentError("No devices found. Set DEVICES in .env.")

OSError: No devices found. Set DEVICES in .env.

PS D:\\Code> python .\\export\_punch\_records.py

Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 204, in \_new\_conn

&#x20;   sock = connection.create\_connection(

&#x20;       (self.\_dns\_host, self.port),

&#x20;   ...<2 lines>...

&#x20;       socket\_options=self.socket\_options,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\connection.py", line 85, in create\_connection

&#x20;   raise err

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\connection.py", line 73, in create\_connection

&#x20;   sock.connect(sa)

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~^^^^

TimeoutError: \[WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond



The above exception was the direct cause of the following exception:



Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 787, in urlopen

&#x20;   response = self.\_make\_request(

&#x20;       conn,

&#x20;   ...<10 lines>...

&#x20;       \*\*response\_kw,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 488, in \_make\_request

&#x20;   raise new\_e

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 464, in \_make\_request

&#x20;   self.\_validate\_conn(conn)

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~^^^^^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 1093, in \_validate\_conn

&#x20;   conn.connect()

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 759, in connect

&#x20;   self.sock = sock = self.\_new\_conn()

&#x20;                      \~\~\~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 213, in \_new\_conn

&#x20;   raise ConnectTimeoutError(

&#x20;   ...<2 lines>...

&#x20;   ) from e

urllib3.exceptions.ConnectTimeoutError: (<HTTPSConnection(host='10.10.80.50', port=443) at 0x23d4923fa10>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)')



The above exception was the direct cause of the following exception:



Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\adapters.py", line 645, in send

&#x20;   resp = conn.urlopen(

&#x20;       method=request.method,

&#x20;   ...<9 lines>...

&#x20;       chunked=chunked,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 841, in urlopen

&#x20;   retries = retries.increment(

&#x20;       method, url, error=new\_e, \_pool=self, \_stacktrace=sys.exc\_info()\[2]

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\retry.py", line 535, in increment

&#x20;   raise MaxRetryError(\_pool, url, reason) from reason  # type: ignore\[arg-type]

&#x20;   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='10.10.80.50', port=443): Max retries exceeded with url: /ISAPI/AccessControl/AcsEvent?format=json (Caused by ConnectTimeoutError(<HTTPSConnection(host='10.10.80.50', port=443) at 0x23d4923fa10>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)'))



During handling of the above exception, another exception occurred:



Traceback (most recent call last):

&#x20; File "D:\\Code\\export\_punch\_records.py", line 161, in \_post\_with\_fallback

&#x20;   response = self.session.post(url, json=payload, timeout=30)

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 640, in post

&#x20;   return self.request("POST", url, data=data, json=json, \*\*kwargs)

&#x20;          \~\~\~\~\~\~\~\~\~\~\~\~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 592, in request

&#x20;   resp = self.send(prep, \*\*send\_kwargs)

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 706, in send

&#x20;   r = adapter.send(request, \*\*kwargs)

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\adapters.py", line 666, in send

&#x20;   raise ConnectTimeout(e, request=request)

requests.exceptions.ConnectTimeout: HTTPSConnectionPool(host='10.10.80.50', port=443): Max retries exceeded with url: /ISAPI/AccessControl/AcsEvent?format=json (Caused by ConnectTimeoutError(<HTTPSConnection(host='10.10.80.50', port=443) at 0x23d4923fa10>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)'))



During handling of the above exception, another exception occurred:



Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 204, in \_new\_conn

&#x20;   sock = connection.create\_connection(

&#x20;       (self.\_dns\_host, self.port),

&#x20;   ...<2 lines>...

&#x20;       socket\_options=self.socket\_options,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\connection.py", line 85, in create\_connection

&#x20;   raise err

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\connection.py", line 73, in create\_connection

&#x20;   sock.connect(sa)

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~^^^^

TimeoutError: \[WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond



The above exception was the direct cause of the following exception:



Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 787, in urlopen

&#x20;   response = self.\_make\_request(

&#x20;       conn,

&#x20;   ...<10 lines>...

&#x20;       \*\*response\_kw,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 493, in \_make\_request

&#x20;   conn.request(

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~^

&#x20;       method,

&#x20;       ^^^^^^^

&#x20;   ...<6 lines>...

&#x20;       enforce\_content\_length=enforce\_content\_length,

&#x20;       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20;   )

&#x20;   ^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 500, in request

&#x20;   self.endheaders()

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "C:\\Program Files\\WindowsApps\\PythonSoftwareFoundation.Python.3.13\_3.13.3568.0\_x64\_\_qbz5n2kfra8p0\\Lib\\http\\client.py", line 1353, in endheaders

&#x20;   self.\_send\_output(message\_body, encode\_chunked=encode\_chunked)

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~\~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20; File "C:\\Program Files\\WindowsApps\\PythonSoftwareFoundation.Python.3.13\_3.13.3568.0\_x64\_\_qbz5n2kfra8p0\\Lib\\http\\client.py", line 1113, in \_send\_output

&#x20;   self.send(msg)

&#x20;   \~\~\~\~\~\~\~\~\~^^^^^

&#x20; File "C:\\Program Files\\WindowsApps\\PythonSoftwareFoundation.Python.3.13\_3.13.3568.0\_x64\_\_qbz5n2kfra8p0\\Lib\\http\\client.py", line 1057, in send

&#x20;   self.connect()

&#x20;   \~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 331, in connect

&#x20;   self.sock = self.\_new\_conn()

&#x20;               \~\~\~\~\~\~\~\~\~\~\~\~\~\~^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connection.py", line 213, in \_new\_conn

&#x20;   raise ConnectTimeoutError(

&#x20;   ...<2 lines>...

&#x20;   ) from e

urllib3.exceptions.ConnectTimeoutError: (<HTTPConnection(host='10.10.80.50', port=80) at 0x23d49348d70>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)')



The above exception was the direct cause of the following exception:



Traceback (most recent call last):

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\adapters.py", line 645, in send

&#x20;   resp = conn.urlopen(

&#x20;       method=request.method,

&#x20;   ...<9 lines>...

&#x20;       chunked=chunked,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\connectionpool.py", line 841, in urlopen

&#x20;   retries = retries.increment(

&#x20;       method, url, error=new\_e, \_pool=self, \_stacktrace=sys.exc\_info()\[2]

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\urllib3\\util\\retry.py", line 535, in increment

&#x20;   raise MaxRetryError(\_pool, url, reason) from reason  # type: ignore\[arg-type]

&#x20;   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

urllib3.exceptions.MaxRetryError: HTTPConnectionPool(host='10.10.80.50', port=80): Max retries exceeded with url: /ISAPI/AccessControl/AcsEvent?format=json (Caused by ConnectTimeoutError(<HTTPConnection(host='10.10.80.50', port=80) at 0x23d49348d70>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)'))



During handling of the above exception, another exception occurred:



Traceback (most recent call last):

&#x20; File "D:\\Code\\export\_punch\_records.py", line 288, in <module>

&#x20;   main()

&#x20;   \~\~\~\~^^

&#x20; File "D:\\Code\\export\_punch\_records.py", line 283, in main

&#x20;   output\_path, row\_count = export\_to\_csv(start\_time, end\_time, Path(args.output))

&#x20;                            \~\~\~\~\~\~\~\~\~\~\~\~\~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20; File "D:\\Code\\export\_punch\_records.py", line 257, in export\_to\_csv

&#x20;   events = client.fetch\_events(start\_time, end\_time)

&#x20; File "D:\\Code\\export\_punch\_records.py", line 143, in fetch\_events

&#x20;   response = self.\_post\_with\_fallback(payload)

&#x20; File "D:\\Code\\export\_punch\_records.py", line 168, in \_post\_with\_fallback

&#x20;   response = self.session.post(

&#x20;       f"{alt\_base}/ISAPI/AccessControl/AcsEvent?format=json",

&#x20;       json=payload,

&#x20;       timeout=30,

&#x20;   )

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 640, in post

&#x20;   return self.request("POST", url, data=data, json=json, \*\*kwargs)

&#x20;          \~\~\~\~\~\~\~\~\~\~\~\~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 592, in request

&#x20;   resp = self.send(prep, \*\*send\_kwargs)

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\sessions.py", line 706, in send

&#x20;   r = adapter.send(request, \*\*kwargs)

&#x20; File "C:\\Users\\MSI\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13\_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\requests\\adapters.py", line 666, in send

&#x20;   raise ConnectTimeout(e, request=request)

requests.exceptions.ConnectTimeout: HTTPConnectionPool(host='10.10.80.50', port=80): Max retries exceeded with url: /ISAPI/AccessControl/AcsEvent?format=json (Caused by ConnectTimeoutError(<HTTPConnection(host='10.10.80.50', port=80) at 0x23d49348d70>, 'Connection to 10.10.80.50 timed out. (connect timeout=30)'))

PS D:\\Code>



