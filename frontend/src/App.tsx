import { Route, Routes } from 'react-router'
import { RequireCapability, Landing } from './session/capabilities'
import { AppShell } from './shell/AppShell'
import { SignIn } from './pages/signin/SignIn'
import { Waiting } from './pages/unavailable/Waiting'
import { Catalog } from './pages/catalog/Catalog'
import { TableView } from './pages/catalog/TableView'
import { SqlExplorer } from './pages/sql/SqlExplorer'
import { RefreshList, RunDetail } from './pages/refresh/Refresh'
import { Dashboard } from './pages/dashboard/Dashboard'
import { Settings } from './pages/settings/Settings'
export function App() {
  return <Routes><Route path="/sign-in" element={<SignIn />} /><Route element={<RequireCapability />}><Route element={<AppShell />}>
    <Route index element={<Landing />} /><Route path="waiting" element={<Waiting />} />
    <Route element={<RequireCapability capability="preview:detail" />}><Route path="catalog" element={<Catalog />} /><Route path="catalog/:datasetKey" element={<TableView />} /></Route>
    <Route element={<RequireCapability capability="sql:execute" />}><Route path="sql" element={<SqlExplorer />} /></Route>
    <Route element={<RequireCapability capability="refresh:read" />}><Route path="refresh" element={<RefreshList />} /><Route path="refresh/:runId" element={<RunDetail />} /></Route>
    <Route element={<RequireCapability capability="national:read" />}><Route path="dashboard" element={<Dashboard />} /></Route>
    <Route element={<RequireCapability capability="settings:read" />}><Route path="settings" element={<Settings />} /></Route>
    <Route element={<RequireCapability capability="settings:write" />}><Route path="setup" element={<Settings setup />} /></Route>
    <Route path="*" element={<Landing />} />
  </Route></Route></Routes>
}
