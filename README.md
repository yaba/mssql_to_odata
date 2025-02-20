# MSSQL to OData Bridge

A lightweight Flask-based service that bridges Microsoft SQL Server with OData, enabling seamless data access for tools like Tableau Public, which does not natively support MSSQL connections.

## Features
- 🚀 **Run as Standalone, Docker, or Composer**
- 🔌 **Connects to MSSQL Server**
- ⚙️ **Configurable SQL Server Details**
- 📊 **Displays Information About Tables, Views, and Their Objects**
- 🌐 **Serves Content as OData for Easy Integration**

## Why This Project?
Tableau Free does not support direct connections to Microsoft SQL Server. This project solves that limitation by exposing MSSQL data as an OData service, which Tableau can easily consume.

## Installation & Usage
### 1. Standalone Mode
```bash
pip install -r requirements.txt
python app.py
```

### 2. Using Docker
```bash
docker build -t mssql-odata-bridge .
docker run -p 5000:5000 mssql-odata-bridge
```

### 3. Using Docker Compose
```bash
docker-compose up -d
```

## Configuration
Upon first run, you will be prompted to configure your SQL Server details. These settings will be stored in a `config/config.json` file.

## Accessing the OData Service
Once running, access your data using:
```
http://localhost:5000/odata/v4/{database}/{table_or_view}
```

## Contributing
Pull requests are welcome! Feel free to open issues for bugs or feature requests.

## Support
☕ Like this project?

[![Buy Me a Coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20Me%20a%20Coffee&emoji=☕&slug=polido&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/polido)




---
MIT License | Created with ❤️ using Flask

