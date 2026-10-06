<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { get } from "svelte/store";

  import { authStore } from "$lib/stores/auth";

  onMount(() => {
    const state = get(authStore);
    if (state.token) {
      goto("/home");
    } else {
      goto("/login");
    }
  });
</script>

<section class="redirect-wrap">
  <p class="redirect-msg"><span class="blink">█</span> redirecionando…</p>
</section>

<style>
  .redirect-wrap {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 60vh;
    font-family: var(--font-mono, monospace);
  }
  .redirect-msg {
    font-size: 0.85rem;
    color: var(--ink-dim, #888);
  }
  .blink {
    animation: blink 1s step-end infinite;
  }
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
</style>
