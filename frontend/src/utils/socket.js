import { io } from 'socket.io-client';
import { API_BASE_URL } from './apiConfig';

// Standardized socket initialization
const socket = io(API_BASE_URL, {
    transports: ['websocket'],
    autoConnect: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
});

export default socket;
