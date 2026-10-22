import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './style.css';
class Boundary extends React.Component<{children:React.ReactNode},{error:string}>{state={error:''};static getDerivedStateFromError(e:Error){return {error:e.message};}render(){return this.state.error?<main className="boot"><h1>RiverGuard needs a restart</h1><p>{this.state.error}</p><button onClick={()=>location.reload()}>Reopen app</button><p>Your saved phone database is retained.</p></main>:this.props.children;}}
createRoot(document.getElementById('root')!).render(<Boundary><App/></Boundary>);
