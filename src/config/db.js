const mysql = require('mysql2');

const pool = mysql.createPool({
  host: 'localhost',
  port: 3308,
  user: 'root',
  password: '1011',
  database: 'chatbot_db',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
});

console.log('Pool MySQL configurado!');

module.exports = pool.promise();