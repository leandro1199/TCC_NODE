const admin = require('firebase-admin');

const serviceAccount = require('../../../json/firebase.json');

if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
}

const dbFirestore = admin.firestore();

module.exports = {
  admin,
  dbFirestore
};