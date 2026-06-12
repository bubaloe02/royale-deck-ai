import React from 'react';
import ReactDOM from 'react-dom/client';
import { ClerkProvider } from '@clerk/react';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <ClerkProvider publishableKey="pk_test_Y2hvaWNlLXNhdHlyLTE2LmNsZXJrLmFjY291bnRzLmRldiQ">
    <App />
  </ClerkProvider>
);
