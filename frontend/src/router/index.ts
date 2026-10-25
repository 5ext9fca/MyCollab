import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '../components/AppLayout.vue'
import LoginView from '../views/LoginView.vue'
import { useAuthStore } from '../stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { guestOnly: true } },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: 'design/templates', name: 'production-templates', component: () => import('../views/ProductionTemplatesView.vue') },
        { path: 'design/:id?', name: 'design', component: () => import('../views/DesignView.vue') },
        { path: '', redirect: { name: 'my-work' } },
        { path: 'my-work', name: 'my-work', component: () => import('../views/MyWorkView.vue') },
        { path: 'notifications', name: 'notifications', component: () => import('../views/NotificationsView.vue') },
        {
          path: 'missions',
          name: 'square',
          component: () => import('../views/MissionSquareView.vue'),
        },
        {
          path: 'workspace',
          name: 'workspace',
          component: () => import('../views/WorkspaceView.vue'),
        },
        {
          path: 'missions/new',
          name: 'mission-create',
          component: () => import('../views/MissionCreateView.vue'),
        },
        {
          path: 'missions/:id',
          name: 'mission-detail',
          component: () => import('../views/MissionDetailView.vue'),
          props: true,
        },
        {
          path: 'claimed',
          name: 'claimed',
          component: () => import('../views/MyClaimedView.vue'),
        },
        {
          path: 'published',
          name: 'published',
          component: () => import('../views/MyPublishedView.vue'),
        },
        {
          path: 'milestones',
          name: 'milestones',
          component: () => import('../views/MilestoneListView.vue'),
        },
        {
          path: 'milestones/:id',
          name: 'milestone-detail',
          component: () => import('../views/MilestoneDetailView.vue'),
          props: true,
        },
        {
          path: 'library',
          name: 'library',
          component: () => import('../views/LibraryView.vue'),
        },
        {
          // SPA admin console. Deliberately not `/admin`, which is Django Admin.
          path: 'manage',
          name: 'manage',
          component: () => import('../views/AdminView.vue'),
          meta: { requiresStaff: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'square' } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) {
    await auth.fetchMe()
  }
  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresStaff && auth.user && !auth.user.is_staff) {
    return { name: 'square' }
  }
  if (to.meta.guestOnly && auth.user) {
    return { name: 'my-work' }
  }
  return true
})
