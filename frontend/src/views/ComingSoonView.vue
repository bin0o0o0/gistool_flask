<script setup lang="ts">
import SiteNav from '@/components/SiteNav.vue'

defineProps<{
  eyebrow: string
  title: string
  description: string
}>()
</script>

<template>
  <div class="reserved-page">
    <SiteNav />

    <main class="reserved-page__main">
      <section class="reserved-panel">
        <p>{{ eyebrow }}</p>
        <h1>{{ title }}</h1>
        <span>{{ description }}</span>
      </section>
    </main>
  </div>
</template>

<style scoped>
.reserved-page {
  min-height: 100vh;
  background:
    linear-gradient(135deg, rgba(2, 13, 31, 0.96), rgba(4, 38, 61, 0.94)),
    #03162d;
  color: #f4fbff;
}

.reserved-page__main {
  display: grid;
  place-items: center;
  width: min(100% - 48px, 1040px);
  min-height: calc(100vh - 112px);
  margin: 0 auto;
  padding: 48px 0;
}

.reserved-panel {
  width: min(100%, 760px);
  padding: clamp(30px, 6vw, 58px);
  border: 1px solid rgba(157, 235, 255, 0.24);
  border-radius: 8px;
  background: rgba(5, 34, 57, 0.52);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.07),
    0 28px 80px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(18px);
}

.reserved-panel p,
.reserved-panel h1,
.reserved-panel span {
  margin: 0;
  letter-spacing: 0;
}

.reserved-panel p {
  color: #86fff0;
  font-weight: 800;
}

.reserved-panel h1 {
  margin-top: 18px;
  color: #f7fff7;
  font-size: clamp(2.4rem, 6vw, 4.2rem);
  line-height: 1.08;
}

.reserved-panel span {
  display: block;
  margin-top: 22px;
  color: rgba(231, 246, 252, 0.82);
  font-size: 1.08rem;
  line-height: 1.9;
}
</style>
