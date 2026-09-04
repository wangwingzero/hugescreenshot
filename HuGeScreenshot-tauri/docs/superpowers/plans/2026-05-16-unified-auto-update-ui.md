# Unified Auto Update UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the top update banner and the settings about page so both surfaces share one updater state machine, support in-app download/install, and show synchronized progress.

**Architecture:** Keep the updater integration in the existing Vue composable layer, but convert `useAutoUpdate()` from per-call local state into a module-scoped shared state source. Both `App.vue` and `AboutSection.vue` will bind to the same state/actions, while settings persistence for `lastCheckTime` and `autoCheck` remains in `settingsStore`.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, Tauri updater plugin

---

### Task 1: Lock Shared Updater Behavior with Tests

**Files:**
- Create: `src/composables/__tests__/useAutoUpdate.test.ts`
- Modify: `src/components/settings/sections/__tests__/AboutSection.test.ts`
- Modify: `src/__tests__/App.wordFormatter.test.ts`

- [ ] **Step 1: Write the failing composable test**

```ts
it('shares updater state across composable consumers', async () => {
  const first = useAutoUpdate()
  const second = useAutoUpdate()

  mockCheck.mockResolvedValueOnce({
    version: '0.1.13',
    body: 'notes',
    downloadAndInstall: vi.fn(),
  })

  await first.checkForUpdate()

  expect(second.status.value).toBe('available')
  expect(second.updateInfo.value?.version).toBe('0.1.13')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:run -- src/composables/__tests__/useAutoUpdate.test.ts`
Expected: FAIL because the second consumer still sees independent local state.

- [ ] **Step 3: Extend AboutSection test with the unified update UI expectation**

```ts
it('shows update action and progress from shared updater state', async () => {
  mockUseAutoUpdateState({
    status: 'downloading',
    updateInfo: { version: '0.1.13', notes: '' },
    downloadProgressText: '42%',
    downloadDetailText: '42% · 4 MB / 10 MB · 1 MB/s',
  })

  const wrapper = mountAboutSection()
  await flushPromises()

  expect(wrapper.text()).toContain('42%')
  expect(wrapper.text()).toContain('0.1.13')
})
```

- [ ] **Step 4: Run AboutSection test to verify it fails**

Run: `npm run test:run -- src/components/settings/sections/__tests__/AboutSection.test.ts`
Expected: FAIL because the section still renders the old invoke-based status text only.

- [ ] **Step 5: Extend App test with banner action expectation**

```ts
it('shows unified update banner action when a shared update is available', async () => {
  mockUseAutoUpdateState({
    status: 'available',
    updateInfo: { version: '0.1.13', notes: '' },
  })

  const wrapper = mount(App)
  await flushPromises()

  expect(wrapper.text()).toContain('立即更新')
  expect(wrapper.text()).toContain('0.1.13')
})
```

- [ ] **Step 6: Run App test to verify it fails**

Run: `npm run test:run -- src/__tests__/App.wordFormatter.test.ts`
Expected: FAIL because the current App test scaffolding does not provide the shared updater state and the banner visibility path is not controlled.

### Task 2: Implement Shared Updater State and Unified About Section

**Files:**
- Modify: `src/composables/useAutoUpdate.ts`
- Modify: `src/components/settings/sections/AboutSection.vue`

- [ ] **Step 1: Add a complete shared status model**

```ts
export type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'installing'
  | 'upToDate'
  | 'error'
```

- [ ] **Step 2: Move updater refs to module scope so all consumers share them**

```ts
const status = ref<UpdateStatus>('idle')
const updateInfo = ref<{ version: string; notes: string } | null>(null)
const error = ref<string | null>(null)
const progress = ref(0)
const totalBytes = ref(0)
```

- [ ] **Step 3: Make `checkForUpdate()` preserve shared state and expose `upToDate`**

```ts
if (update) {
  status.value = 'available'
  updateInfo.value = { version: update.version, notes: update.body ?? '' }
  return true
}

status.value = 'upToDate'
updateInfo.value = null
return false
```

- [ ] **Step 4: Refactor AboutSection to consume the composable instead of `invoke('check_for_update')`**

```ts
const {
  status: updateStatus,
  updateInfo,
  error: updateError,
  downloadProgressText,
  downloadDetailText,
  checkForUpdate,
  downloadAndInstall,
} = useAutoUpdate()
```

- [ ] **Step 5: Replace the old check-result-only UI with shared controls**

```vue
<button
  class="check-now-btn"
  :disabled="isBusy"
  @click="handlePrimaryAction"
>
  {{ primaryActionText }}
</button>
<span v-if="statusMessage" class="check-result" :class="statusClass">
  {{ statusMessage }}
</span>
<div v-if="showInlineProgress" class="inline-progress-track">
  <div class="inline-progress-bar" :style="{ width: progressWidth }"></div>
</div>
```

- [ ] **Step 6: Re-run the focused tests**

Run: `npm run test:run -- src/composables/__tests__/useAutoUpdate.test.ts src/components/settings/sections/__tests__/AboutSection.test.ts`
Expected: PASS

### Task 3: Wire App Banner to the Same Shared State and Verify

**Files:**
- Modify: `src/App.vue`
- Modify: `src/__tests__/App.wordFormatter.test.ts`

- [ ] **Step 1: Keep banner visibility derived from shared updater state**

```ts
const shouldRenderUpdateBanner = computed(() =>
  showUpdateBanner.value &&
  (updateStatus.value === 'available' ||
    updateStatus.value === 'downloading' ||
    updateStatus.value === 'installing' ||
    updateStatus.value === 'error') &&
  updateInfo.value,
)
```

- [ ] **Step 2: Ensure manual banner dismissal does not cancel shared download/install state**

```ts
function dismissUpdateBanner() {
  if (updateStatus.value === 'downloading' || updateStatus.value === 'installing') return
  showUpdateBanner.value = false
}
```

- [ ] **Step 3: Update App test mocks to exercise unified banner copy**

```ts
vi.mock('@/composables/useAutoUpdate', () => ({
  useAutoUpdate: () => mockAutoUpdateState,
}))
```

- [ ] **Step 4: Run App test to verify it passes**

Run: `npm run test:run -- src/__tests__/App.wordFormatter.test.ts`
Expected: PASS

### Task 4: Final Regression Verification

**Files:**
- Modify: `src/components/settings/sections/__tests__/AboutSection.test.ts`
- Modify: `src/__tests__/App.wordFormatter.test.ts`
- Modify: `src/composables/__tests__/useAutoUpdate.test.ts`

- [ ] **Step 1: Run the targeted update-related frontend tests**

Run: `npm run test:run -- src/composables/__tests__/useAutoUpdate.test.ts src/components/settings/sections/__tests__/AboutSection.test.ts src/__tests__/App.wordFormatter.test.ts`
Expected: PASS with 0 failures

- [ ] **Step 2: Run a production-oriented frontend build check**

Run: `npm run build`
Expected: exit code 0

- [ ] **Step 3: Review changed files for scope control**

Run: `git diff -- src/composables/useAutoUpdate.ts src/components/settings/sections/AboutSection.vue src/components/settings/sections/__tests__/AboutSection.test.ts src/__tests__/App.wordFormatter.test.ts src/composables/__tests__/useAutoUpdate.test.ts src/App.vue`
Expected: diff only shows the unified update UI and related tests
