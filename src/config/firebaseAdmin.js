const admin = require('firebase-admin');

let app;

if (!admin.apps.length) {

  const serviceAccount = JSON.parse(
    process.env.FIREBASE_SERVICE_ACCOUNT
  );

  app = admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });

} else {

  app = admin.app();

}

const dbFirestore = admin.firestore();

module.exports = {
  admin,
  dbFirestore
};