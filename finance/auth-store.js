// Store a non-extractable PBKDF2 base key, never the plaintext password.
// The key still grants access to reports on this origin; this is not hardware-backed protection.
const DB='finance-crypto-keys', STORE='keys';
function database(){return new Promise((resolve,reject)=>{const request=indexedDB.open(DB,1);request.onupgradeneeded=()=>request.result.createObjectStore(STORE);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)})}
async function operation(mode,action){const db=await database();try{return await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,mode),req=action(tx.objectStore(STORE));req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);tx.onerror=()=>reject(tx.error)})}finally{db.close()}}
export const importPassword=password=>crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
export const loadKey=id=>operation('readonly',store=>store.get(id));
export const saveKey=(id,key)=>operation('readwrite',store=>store.put(key,id));
export const deleteKey=id=>operation('readwrite',store=>store.delete(id));
