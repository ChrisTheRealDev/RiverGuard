import {Component} from 'react';
import type {ReactNode} from 'react';
import {RefreshCw,Waves} from 'lucide-react';
export default class ErrorBoundary extends Component<{children:ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 render(){if(!this.state.failed)return this.props.children;return <main className="boot-screen"><Waves size={36}/><section className="surface view-error" role="alert"><h1>Unable to display this view</h1><p>RiverGuard hit an unexpected display problem. Reload the overview to continue; this does not clear your saved readings or chats.</p><button className="button primary" onClick={()=>location.assign('/')}><RefreshCw size={17}/> Reload overview</button></section></main>;}
}
