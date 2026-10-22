import {Component,type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';
class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<main className="welcome"><div className="glass welcome-card"><h1>Let’s reopen your river.</h1><p>The interface couldn’t finish opening. Your saved readings have not been cleared.</p><button className="primary" onClick={()=>location.reload()}>Reload RiverGuard</button></div></main>:this.props.children;}}
createRoot(document.getElementById('root')!).render(<Boundary><App/></Boundary>);
