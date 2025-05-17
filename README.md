# court-pipeline
This repo is an end to end pipeline to download, extract, transform court decisions  from xml files from the OPENDATA archives, and finally load the transformed data into a database whose data is then exposed via secure API.

### Instructions

1. First of all, clone this repository using this command
```
git clone https://github.com/debisic/judicial-decisions-api.git
```
2. Once step one is complete, get into the folder that contains the source code
```
cd judicial-decisions-api
```
3. Build and run the docker images needed as follows:

```
docker-compose up --build
```
Three containers will be launched, wait to confirm them.
- db container
- data process container
- api container

4. launch the api by following the url displayed on your terminal in the api container or simply copy and paste this in your browser address bar

```
http://localhost:8000/decisions
```

Login authentication will be demanded so for this project the login details are
```
username= admin
password= password
```

### Project Plan
```
.
├── docker-compose.yml
├── LICENSE
├── README.md
├── requirement.txt
└── src
    ├── api
    │   ├── api.py
    │   └── Dockerfile.api
    └── data_processing
        ├── Dockerfile.proc
        ├── entrypoint.sh
        └── pipeline.py
```

## Tasks 
This project is subdivided into 2 major set of tasks, the first part is the <span style="color:green">data_processing</span> the other is the <span style="color:yellow">api</span> which are both subfolders as shown in the tree above.

### data_processing:
Here tar files(tar.gz) are downloaded, then extracted into folders, each folder contains at least one xml file. The ```pipeline.py``` file recursively treats each folder and finally stores unique data in the postgres database.

### api:

This is a REST API that provides the following functionalities and all in json format.
- secure login/authentication 

- display all court decisions as in the below query.
```
http://localhost:8000/decisions
```

- filter decisions by ```chambre``` for example to display all decisions partaining to ```chambre_civile```, this would be the query format.

```
http://localhost:8000/decisions?chambre=chambre_civile
```

- output the contents ```contenu``` of a decision using the decision id ```text_id```
```
http://localhost:8000/decisions/JURITEXT000048283805
```

- text search capability with relevance ranking: for the search word ```Derichebourg```, the text search query would looklike this:
```
http://localhost:8000/decisions?search=Derichebourg
```

<!-- - API accessible online -->

> [!NOTE]  
> The data used in this project belongs to [DILA](https://dila.premier-ministre.gouv.fr/) and was accessed from the [OPENDATA](https://echanges.dila.gouv.fr/OPENDATA/CASS/) archives.

